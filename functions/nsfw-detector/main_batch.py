"""
NSFW 图像检测器 - 批处理优化版本
使用动态批处理提高吞吐量
"""

import os
import io
import base64
import json
import logging
import threading
import queue
import time
from typing import Union, List, Dict, Any
import numpy as np
from PIL import Image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局变量
model = None
processor = None
device = "cpu"

# 批处理配置
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "4"))
BATCH_TIMEOUT_MS = int(os.getenv("BATCH_TIMEOUT_MS", "10"))

# 批处理队列
request_queue = queue.Queue()
results_map = {}
map_lock = threading.Lock()
batch_thread = None


def init_context(context):
    """Nuclio 初始化函数"""
    global model, processor, device, batch_thread
    
    logger.info(f"初始化模型... BATCH_SIZE={BATCH_SIZE}")
    
    try:
        import torch
        
        device = os.getenv("DEVICE", "cpu")
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        
        from transformers import AutoModelForImageClassification, AutoImageProcessor
        
        model_name = os.getenv("NSFW_MODEL_NAME", "Falconsai/nsfw_image_detection")
        cache_dir = "/opt/huggingface/models"
        
        if os.path.exists(cache_dir):
            try:
                processor = AutoImageProcessor.from_pretrained(
                    model_name, cache_dir=cache_dir, local_files_only=True
                )
                model = AutoModelForImageClassification.from_pretrained(
                    model_name, cache_dir=cache_dir, local_files_only=True
                )
            except:
                processor = AutoImageProcessor.from_pretrained(model_name)
                model = AutoModelForImageClassification.from_pretrained(model_name)
        else:
            processor = AutoImageProcessor.from_pretrained(model_name)
            model = AutoModelForImageClassification.from_pretrained(model_name)
        
        model.eval()
        
        # 预热 - 批处理预热
        logger.info("模型预热中...")
        dummy_images = [Image.new('RGB', (224, 224), color='white') for _ in range(BATCH_SIZE)]
        inputs = processor(images=dummy_images, return_tensors="pt")
        with torch.no_grad():
            _ = model(**inputs)
        logger.info("模型预热完成")
        
        # 启动批处理线程
        if BATCH_SIZE > 1:
            logger.info(f"启动批处理线程，batch_size={BATCH_SIZE}")
            batch_thread = threading.Thread(target=_batch_processor, daemon=True)
            batch_thread.start()
        
    except Exception as e:
        logger.error(f"模型初始化失败: {e}")
        raise


def _detect_batch(images: List[Image.Image]) -> List[Dict[str, Any]]:
    """批量图片检测 - 核心优化"""
    global model, processor
    
    if not images:
        return []
    
    import torch
    
    # 批量预处理 - 一次处理所有图片
    inputs = processor(images=images, return_tensors="pt")
    
    if device == "cuda":
        inputs = {k: v.to("cuda") for k, v in inputs.items()}
    
    # 批量推理 - 关键优化点
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
    """后台批处理线程"""
    logger.info("批处理线程已启动")
    
    while True:
        batch_items = []
        batch_images = []
        
        # 收集请求直到达到 BATCH_SIZE 或超时
        start_time = time.time()
        timeout_sec = BATCH_TIMEOUT_MS / 1000.0
        
        while len(batch_items) < BATCH_SIZE:
            elapsed = time.time() - start_time
            remaining = timeout_sec - elapsed
            
            if remaining <= 0 and len(batch_items) > 0:
                break
            
            try:
                wait_time = max(0.001, remaining) if remaining > 0 else 0.001
                item = request_queue.get(timeout=wait_time)
                batch_items.append(item)
                batch_images.append(item['image'])
            except queue.Empty:
                if len(batch_items) > 0:
                    break
                continue
        
        if batch_items:
            try:
                start_infer = time.time()
                results = _detect_batch(batch_images)
                infer_time = (time.time() - start_infer) * 1000
                
                logger.debug(f"批处理完成: {len(batch_items)} 张图片, 耗时 {infer_time:.1f}ms")
                
                # 分发结果
                for i, item in enumerate(batch_items):
                    request_id = item['request_id']
                    with map_lock:
                        results_map[request_id] = results[i]
                    item['event'].set()
                    
            except Exception as e:
                logger.error(f"批处理错误: {e}")
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
    try:
        if isinstance(event.body, bytes):
            body = json.loads(event.body.decode('utf-8'))
        elif isinstance(event.body, str):
            body = json.loads(event.body)
        else:
            body = event.body
        
        # URL 检测
        if 'url' in body:
            import requests
            response = requests.get(body['url'], timeout=30)
            response.raise_for_status()
            image = preprocess_image(response.content)
            
            if BATCH_SIZE > 1:
                result = _process_with_batch(image)
            else:
                result = _detect_batch([image])[0]
            
            return context.Response(
                body=json.dumps({"success": True, "data": result}),
                headers={"Content-Type": "application/json"},
                status_code=200
            )
        
        # base64 图片检测
        elif 'image' in body:
            image = preprocess_image(body['image'])
            
            if BATCH_SIZE > 1:
                result = _process_with_batch(image)
            else:
                result = _detect_batch([image])[0]
            
            return context.Response(
                body=json.dumps({"success": True, "data": result}),
                headers={"Content-Type": "application/json"},
                status_code=200
            )
        
        # 客户端批量检测
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
            return context.Response(
                body=json.dumps({"success": False, "error": "请提供 'image'、'url' 或 'images' 字段"}),
                headers={"Content-Type": "application/json"},
                status_code=400
            )
    
    except Exception as e:
        logger.exception("处理请求时发生错误")
        return context.Response(
            body=json.dumps({"success": False, "error": str(e)}),
            headers={"Content-Type": "application/json"},
            status_code=500
        )


def _process_with_batch(image: Image.Image) -> Dict[str, Any]:
    """使用动态批处理处理单张图片"""
    import time
    import threading
    
    request_id = f"{time.time()}_{threading.current_thread().ident}"
    event = threading.Event()
    
    item = {
        'request_id': request_id,
        'image': image,
        'event': event
    }
    
    # 加入队列
    try:
        request_queue.put(item, timeout=5)
    except queue.Full:
        # 队列满，直接处理
        return _detect_batch([image])[0]
    
    # 等待结果
    event.wait(timeout=30)
    
    with map_lock:
        result = results_map.pop(request_id, None)
    
    if result is None:
        # 超时或其他问题，直接处理
        return _detect_batch([image])[0]
    
    return result
