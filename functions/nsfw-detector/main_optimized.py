"""
NSFW 图像检测器 - 性能优化版本
优化点：
1. 支持批处理推理
2. 动态批处理收集
3. 优化的线程配置
4. ONNX 支持（可选）
"""

import os
import io
import base64
import json
import logging
import threading
import queue
import time
from typing import Union, List, Dict, Any, Optional
import numpy as np
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局变量
model = None
processor = None
device = "cpu"

# 批处理配置
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1"))
BATCH_TIMEOUT_MS = int(os.getenv("BATCH_TIMEOUT_MS", "50"))  # 最大等待时间
MAX_QUEUE_SIZE = int(os.getenv("MAX_QUEUE_SIZE", "100"))

USE_DYNAMIC_BATCH = BATCH_SIZE > 1

# 动态批处理队列（仅当启用批处理时使用）
request_queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
response_dict = {}
batch_thread = None
batch_lock = threading.Lock()


def init_context(context):
    """Nuclio 初始化函数"""
    global model, processor, device, batch_thread
    
    logger.info(f"正在初始化 NSFW 检测模型... BATCH_SIZE={BATCH_SIZE}")
    
    try:
        import torch
        
        device = os.getenv("DEVICE", "cpu")
        
        # 设置 PyTorch 线程数
        threads = int(os.getenv("PYTORCH_NUM_THREADS", "1"))
        torch.set_num_threads(threads)
        torch.set_num_interop_threads(threads)
        logger.info(f"PyTorch 线程数: {threads}")
        
        from transformers import AutoModelForImageClassification, AutoImageProcessor
        
        model_name = os.getenv("NSFW_MODEL_NAME", "Falconsai/nsfw_image_detection")
        cache_dir = "/opt/huggingface/models"
        
        logger.info(f"加载模型: {model_name}, 设备: {device}")
        
        if os.path.exists(cache_dir):
            try:
                processor = AutoImageProcessor.from_pretrained(
                    model_name, cache_dir=cache_dir, local_files_only=True
                )
                model = AutoModelForImageClassification.from_pretrained(
                    model_name, cache_dir=cache_dir, local_files_only=True
                )
                logger.info("模型从本地缓存加载成功")
            except Exception as e:
                logger.warning(f"本地缓存加载失败: {e}")
                processor = AutoImageProcessor.from_pretrained(model_name)
                model = AutoModelForImageClassification.from_pretrained(model_name)
        else:
            processor = AutoImageProcessor.from_pretrained(model_name)
            model = AutoModelForImageClassification.from_pretrained(model_name)
        
        if device == "cuda" and torch.cuda.is_available():
            model = model.to("cuda")
            logger.info("模型已加载到 GPU")
        
        # 评估模式（禁用 dropout 等，提高推理速度）
        model.eval()
        
        # 启用推理优化
        if hasattr(model, 'half') and device == "cuda":
            # FP16 在 CPU 上可能更慢，只在 GPU 使用
            pass  # 暂时不启用 FP16，避免精度问题
        
        logger.info("NSFW 检测模型初始化完成")
        
        # 预热
        logger.info("模型预热中...")
        dummy_image = Image.new('RGB', (224, 224), color='white')
        for _ in range(3):
            _detect_single(dummy_image)
        logger.info("模型预热完成")
        
        # 启动批处理线程（如果启用）
        if USE_DYNAMIC_BATCH:
            logger.info(f"启动动态批处理线程，批大小={BATCH_SIZE}")
            batch_thread = threading.Thread(target=_batch_processor, daemon=True)
            batch_thread.start()
        
    except Exception as e:
        logger.error(f"模型初始化失败: {e}")
        raise


def _detect_single(image: Image.Image) -> Dict[str, Any]:
    """单张图片检测（内部函数）"""
    global model, processor
    
    inputs = processor(images=image, return_tensors="pt")
    
    if device == "cuda":
        inputs = {k: v.to("cuda") for k, v in inputs.items()}
    
    import torch
    with torch.no_grad():
        outputs = model(**inputs)
        probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)
    
    probs = probabilities[0].cpu().numpy()
    labels = model.config.id2label
    
    scores = {labels[i]: float(probs[i]) for i in range(len(labels))}
    predicted_class = labels[int(np.argmax(probs))]
    confidence = float(np.max(probs))
    
    is_nsfw = predicted_class.lower() in ['nsfw', 'unsafe', 'adult', 'porn', 'hentai', 'sexy']
    
    return {
        "is_nsfw": is_nsfw,
        "predicted_class": predicted_class,
        "confidence": round(confidence, 4),
        "scores": {k: round(v, 4) for k, v in scores.items()}
    }


def _detect_batch(images: List[Image.Image]) -> List[Dict[str, Any]]:
    """批量图片检测"""
    global model, processor
    
    if not images:
        return []
    
    import torch
    
    # 批量预处理
    inputs = processor(images=images, return_tensors="pt")
    
    if device == "cuda":
        inputs = {k: v.to("cuda") for k, v in inputs.items()}
    
    with torch.no_grad():
        outputs = model(**inputs)
        probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)
    
    results = []
    labels = model.config.id2label
    
    for i in range(len(images)):
        probs = probabilities[i].cpu().numpy()
        scores = {labels[j]: float(probs[j]) for j in range(len(labels))}
        predicted_class = labels[int(np.argmax(probs))]
        confidence = float(np.max(probs))
        is_nsfw = predicted_class.lower() in ['nsfw', 'unsafe', 'adult', 'porn', 'hentai', 'sexy']
        
        results.append({
            "is_nsfw": is_nsfw,
            "predicted_class": predicted_class,
            "confidence": round(confidence, 4),
            "scores": {k: round(v, 4) for k, v in scores.items()}
        })
    
    return results


def _batch_processor():
    """批处理后台线程"""
    global request_queue, response_dict
    
    logger.info("批处理线程已启动")
    
    while True:
        batch_items = []
        batch_images = []
        
        # 收集请求
        start_time = time.time()
        timeout = BATCH_TIMEOUT_MS / 1000.0
        
        while len(batch_items) < BATCH_SIZE:
            elapsed = time.time() - start_time
            remaining = timeout - elapsed
            
            if remaining <= 0 and len(batch_items) > 0:
                break
            
            try:
                item = request_queue.get(timeout=max(0.001, remaining) if remaining > 0 else 0.001)
                batch_items.append(item)
                batch_images.append(item['image'])
            except queue.Empty:
                if len(batch_items) > 0:
                    break
                continue
        
        if batch_items:
            try:
                # 批量推理
                results = _detect_batch(batch_images)
                
                # 分发结果
                for i, item in enumerate(batch_items):
                    request_id = item['request_id']
                    with batch_lock:
                        response_dict[request_id] = results[i]
                    
                    # 通知等待的线程
                    item['event'].set()
                    
            except Exception as e:
                logger.error(f"批处理错误: {e}")
                # 返回错误给所有等待的请求
                for item in batch_items:
                    item['event'].set()


def preprocess_image(image_data: Union[str, bytes]) -> Image.Image:
    """预处理图像数据"""
    if isinstance(image_data, str):
        image_bytes = base64.b64decode(image_data)
    else:
        image_bytes = image_data
    
    image = Image.open(io.BytesIO(image_bytes))
    
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    return image


def handler(context, event):
    """Nuclio 处理函数"""
    global request_queue, response_dict
    
    try:
        # 解析请求体
        if isinstance(event.body, bytes):
            body = json.loads(event.body.decode('utf-8'))
        elif isinstance(event.body, str):
            body = json.loads(event.body)
        else:
            body = event.body
        
        # 单张图片检测
        if 'image' in body:
            image = preprocess_image(body['image'])
            
            if USE_DYNAMIC_BATCH:
                # 使用动态批处理
                request_id = str(time.time()) + str(threading.current_thread().ident)
                event_flag = threading.Event()
                
                item = {
                    'request_id': request_id,
                    'image': image,
                    'event': event_flag
                }
                
                try:
                    request_queue.put(item, timeout=5)
                except queue.Full:
                    # 队列满，降级为直接处理
                    result = _detect_single(image)
                    return _make_response(result)
                
                # 等待结果
                event_flag.wait(timeout=30)
                
                with batch_lock:
                    result = response_dict.pop(request_id, None)
                
                if result is None:
                    result = _detect_single(image)
                
                return _make_response(result)
            else:
                # 直接处理
                result = _detect_single(image)
                return _make_response(result)
        
        # URL 检测
        elif 'url' in body:
            import requests
            response = requests.get(body['url'], timeout=30)
            response.raise_for_status()
            image = preprocess_image(response.content)
            result = _detect_single(image)
            return _make_response(result)
        
        # 批量检测（客户端批量）
        elif 'images' in body:
            images_data = body['images']
            images = [preprocess_image(d) for d in images_data]
            results = _detect_batch(images)
            
            return context.Response(
                body=json.dumps({
                    "success": True,
                    "batch_size": len(results),
                    "data": [{"success": True, "data": r} for r in results]
                }),
                headers={"Content-Type": "application/json"},
                status_code=200
            )
        
        else:
            return _make_error_response("请提供 'image'、'url' 或 'images' 字段")
    
    except Exception as e:
        logger.exception("处理请求时发生错误")
        return _make_error_response(str(e))


def _make_response(data):
    """构建成功响应"""
    import json
    from nuclio_sdk import Response
    
    body = json.dumps({"success": True, "data": data})
    return Response(body=body, headers={"Content-Type": "application/json"}, status_code=200)


def _make_error_response(error_msg):
    """构建错误响应"""
    import json
    from nuclio_sdk import Response
    
    body = json.dumps({"success": False, "error": error_msg})
    return Response(body=body, headers={"Content-Type": "application/json"}, status_code=400)
