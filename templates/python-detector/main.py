"""
检测器模板
基于 Nuclio 的 AI 检测器示例实现

功能：请在此描述你的检测器功能
"""

import os
import io
import base64
import json
import logging
from typing import Union, Dict, Any
from PIL import Image

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局变量 - 模型只加载一次
model = None


def init_context(context):
    """
    Nuclio 初始化函数 - 在容器启动时调用一次
    用于加载模型、初始化资源等
    """
    global model
    
    logger.info("正在初始化检测模型...")
    
    try:
        # TODO: 在这里加载你的模型
        # 示例：
        # from transformers import pipeline
        # model_name = os.getenv("MODEL_NAME", "default-model")
        # model = pipeline("image-classification", model=model_name)
        
        # 当前为示例：模拟模型
        model = {"loaded": True, "device": os.getenv("DEVICE", "cpu")}
        
        logger.info("模型初始化完成")
        
    except Exception as e:
        logger.error(f"模型初始化失败: {e}")
        raise


def preprocess_input(data: Union[str, bytes, dict]) -> Any:
    """
    预处理输入数据
    
    Args:
        data: 可以是 base64 字符串、字节数据或字典
    
    Returns:
        处理后的输入，格式取决于你的模型需求
    """
    # TODO: 根据你的检测器需求实现预处理
    
    # 示例：处理 base64 图片
    if isinstance(data, str):
        image_bytes = base64.b64decode(data)
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        return image
    
    # 示例：处理 URL
    if isinstance(data, dict) and 'url' in data:
        import requests
        response = requests.get(data['url'], timeout=30)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        return image
    
    return data


def detect(input_data: Any) -> Dict[str, Any]:
    """
    执行检测
    
    Args:
        input_data: 预处理后的输入数据
    
    Returns:
        检测结果字典
    """
    global model
    
    # TODO: 实现你的检测逻辑
    
    # 示例返回格式
    return {
        "result": "example_result",
        "confidence": 0.95,
        "details": {
            "input_shape": str(input_data.size) if hasattr(input_data, 'size') else "unknown"
        }
    }


def handler(context, event):
    """
    Nuclio 处理函数 - 每个请求调用
    
    支持的调用方式（根据需求自定义）：
    1. 单张图片：{"image": "base64_encoded_image"}
    2. URL 检测：{"url": "http://example.com/image.jpg"}
    3. 批量检测：{"images": ["base64_1", "base64_2"]}
    4. 文本输入：{"text": "要分析的文本"}
    """
    try:
        # 解析请求体
        if isinstance(event.body, bytes):
            body = json.loads(event.body.decode('utf-8'))
        elif isinstance(event.body, str):
            body = json.loads(event.body)
        else:
            body = event.body
        
        # TODO: 根据你的检测器需求处理不同类型的输入
        
        # 示例：单张图片检测
        if 'image' in body:
            input_data = preprocess_input(body['image'])
            result = detect(input_data)
            return context.Response(
                body=json.dumps({
                    "success": True,
                    "data": result
                }),
                headers={"Content-Type": "application/json"},
                status_code=200
            )
        
        # 示例：URL 检测
        elif 'url' in body:
            input_data = preprocess_input({'url': body['url']})
            result = detect(input_data)
            return context.Response(
                body=json.dumps({
                    "success": True,
                    "data": result
                }),
                headers={"Content-Type": "application/json"},
                status_code=200
            )
        
        # 示例：批量检测
        elif 'images' in body:
            results = []
            for img_data in body['images']:
                try:
                    input_data = preprocess_input(img_data)
                    result = detect(input_data)
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
