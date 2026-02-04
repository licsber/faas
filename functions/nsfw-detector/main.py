"""
NSFW 图像检测器
使用 transformers 库的 nsfw-detection 模型
"""

import os
import io
import base64
import json
import logging
from typing import Union, List, Dict, Any
import numpy as np
from PIL import Image

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局变量 - 模型只加载一次
model = None
processor = None


def init_context(context):
    """
    Nuclio 初始化函数 - 在容器启动时调用一次
    """
    global model, processor
    
    logger.info("正在初始化 NSFW 检测模型...")
    
    try:
        # 使用 transformers 的 pipeline 进行 NSFW 检测
        from transformers import AutoModelForImageClassification, AutoImageProcessor
        
        # 使用 Folk-Lab/NSFW-Detect 模型（轻量级，适合 FaaS）
        model_name = os.getenv("NSFW_MODEL_NAME", "Falconsai/nsfw_image_detection")
        device = os.getenv("DEVICE", "cpu")
        
        logger.info(f"加载模型: {model_name}, 设备: {device}")
        
        processor = AutoImageProcessor.from_pretrained(model_name)
        model = AutoModelForImageClassification.from_pretrained(model_name)
        
        if device == "cuda" and model.cuda.is_available():
            model = model.to("cuda")
            logger.info("模型已加载到 GPU")
        else:
            logger.info("模型已加载到 CPU")
        
        logger.info("NSFW 检测模型初始化完成")
        
    except Exception as e:
        logger.error(f"模型初始化失败: {e}")
        raise


def preprocess_image(image_data: Union[str, bytes]) -> Image.Image:
    """
    预处理图像数据
    
    Args:
        image_data: base64 编码的字符串或原始字节
    
    Returns:
        PIL Image 对象
    """
    if isinstance(image_data, str):
        # base64 编码
        image_bytes = base64.b64decode(image_data)
    else:
        image_bytes = image_data
    
    image = Image.open(io.BytesIO(image_bytes))
    
    # 转换为 RGB（处理 PNG 的透明通道等）
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    return image


def detect_nsfw(image: Image.Image) -> Dict[str, Any]:
    """
    对单张图片进行 NSFW 检测
    
    Args:
        image: PIL Image 对象
    
    Returns:
        包含检测结果的字典
    """
    global model, processor
    
    # 预处理图像
    inputs = processor(images=image, return_tensors="pt")
    
    # 移动到 GPU（如果可用）
    if os.getenv("DEVICE") == "cuda" and model.device.type != "cpu":
        inputs = {k: v.to("cuda") for k, v in inputs.items()}
    
    # 推理
    import torch
    with torch.no_grad():
        outputs = model(**inputs)
        probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)
    
    # 获取预测结果
    probs = probabilities[0].cpu().numpy()
    labels = model.config.id2label
    
    # 构建结果
    scores = {labels[i]: float(probs[i]) for i in range(len(labels))}
    predicted_class = labels[int(np.argmax(probs))]
    confidence = float(np.max(probs))
    
    # 判断是否为 NSFW
    is_nsfw = predicted_class.lower() in ['nsfw', 'unsafe', 'adult', 'porn', 'hentai', 'sexy']
    
    return {
        "is_nsfw": is_nsfw,
        "predicted_class": predicted_class,
        "confidence": round(confidence, 4),
        "scores": {k: round(v, 4) for k, v in scores.items()}
    }


def handler(context, event):
    """
    Nuclio 处理函数 - 每个请求调用
    
    支持两种调用方式：
    1. 单张图片检测：{"image": "base64_encoded_image"}
    2. 批量检测：{"images": ["base64_encoded_image1", "base64_encoded_image2"]}
    3. URL 检测：{"url": "http://example.com/image.jpg"}
    """
    try:
        # 解析请求体
        if isinstance(event.body, bytes):
            body = json.loads(event.body.decode('utf-8'))
        elif isinstance(event.body, str):
            body = json.loads(event.body)
        else:
            body = event.body  # 已经是字典
        
        # 单张图片检测
        if 'image' in body:
            image = preprocess_image(body['image'])
            result = detect_nsfw(image)
            return context.Response(
                body=json.dumps({
                    "success": True,
                    "data": result
                }),
                headers={"Content-Type": "application/json"},
                status_code=200
            )
        
        # URL 检测
        elif 'url' in body:
            import requests
            response = requests.get(body['url'], timeout=30)
            response.raise_for_status()
            image = preprocess_image(response.content)
            result = detect_nsfw(image)
            return context.Response(
                body=json.dumps({
                    "success": True,
                    "data": result
                }),
                headers={"Content-Type": "application/json"},
                status_code=200
            )
        
        # 批量检测
        elif 'images' in body:
            images_data = body['images']
            results = []
            
            for img_data in images_data:
                try:
                    image = preprocess_image(img_data)
                    result = detect_nsfw(image)
                    results.append({"success": True, "data": result})
                except Exception as e:
                    results.append({"success": False, "error": str(e)})
            
            return context.Response(
                body=json.dumps({
                    "success": True,
                    "batch_size": len(results),
                    "data": results
                }),
                headers={"Content-Type": "application/json"},
                status_code=200
            )
        
        else:
            return context.Response(
                body=json.dumps({
                    "success": False,
                    "error": "请求参数错误，请提供 'image'、'url' 或 'images' 字段"
                }),
                headers={"Content-Type": "application/json"},
                status_code=400
            )
    
    except json.JSONDecodeError as e:
        return context.Response(
            body=json.dumps({
                "success": False,
                "error": f"JSON 解析错误: {str(e)}"
            }),
            headers={"Content-Type": "application/json"},
            status_code=400
        )
    
    except Exception as e:
        logger.exception("处理请求时发生错误")
        return context.Response(
            body=json.dumps({
                "success": False,
                "error": str(e)
            }),
            headers={"Content-Type": "application/json"},
            status_code=500
        )
