# 添加新检测器指南

本文档说明如何基于模板添加新的 AI 检测器到平台。

## 快速开始

```bash
# 1. 复制模板创建新检测器
cp -r templates/python-detector functions/my-detector

# 2. 修改配置文件中的 TODO 项
#    - function.yaml: metadata.name, description, build.path
#    - function-gpu.yaml: 同上

# 3. 实现 main.py 中的检测逻辑

# 4. 部署测试
make deploy FUNCTION=my-detector
```

## 详细步骤

### 1. 创建检测器目录

```bash
cp -r templates/python-detector functions/my-detector
```

### 2. 修改 CPU 配置 (function.yaml)

```yaml
metadata:
  name: my-detector          # ← 修改：唯一名称
  labels:
    app: my-detector         # ← 修改

spec:
  description: "人脸检测服务" # ← 修改：功能描述
  
  env:
    - name: MODEL_NAME
      value: "facenet-model" # ← 修改：你的模型名称
  
  build:
    path: ./functions/my-detector  # ← 修改：正确路径
    commands:
      # ← 修改：添加你的依赖
      - pip install --no-cache-dir opencv-python facenet-pytorch
```

### 3. 修改 GPU 配置 (function-gpu.yaml)

同上，注意：
- `metadata.name` 要加 `-gpu` 后缀（如 `my-detector-gpu`）
- `DEVICE` 环境变量设为 `cuda`

### 4. 实现检测逻辑 (main.py)

```python
def init_context(context):
    """初始化模型"""
    global model
    # 加载你的模型
    model = load_model()

def handler(context, event):
    """处理请求"""
    body = json.loads(event.body)
    
    # 执行检测
    result = model.detect(body['image'])
    
    return context.Response(
        body=json.dumps({"success": True, "data": result}),
        headers={"Content-Type": "application/json"}
    )
```

### 5. 部署

```bash
# 仅部署此检测器
make deploy FUNCTION=my-detector

# 或部署 GPU 版本
make deploy FUNCTION=my-detector CUDA=true

# 部署所有检测器
make deploy
```

## 输入/输出规范建议

### 请求格式

```json
// 单张图片
{
    "image": "base64_encoded_string"
}

// URL
{
    "url": "https://example.com/image.jpg"
}

// 批量
{
    "images": ["base64_1", "base64_2"]
}
```

### 响应格式

```json
{
    "success": true,
    "data": {
        // 你的检测结果
    }
}
```

错误时：
```json
{
    "success": false,
    "error": "错误信息"
}
```

## 常用模型示例

| 检测类型 | 推荐模型 | pip 依赖 |
|----------|----------|----------|
| 图像分类 | `google/vit-base-patch16-224` | transformers, torch |
| 目标检测 | `ultralytics/yolov8` | ultralytics |
| 人脸检测 | `opencv` + `dlib` | opencv-python, dlib |
| OCR | `paddleocr` | paddleocr, paddlepaddle |
| 文本分类 | `bert-base-chinese` | transformers, torch |

## 调试技巧

1. **本地测试**：先在本地用 Python 直接运行 main.py 测试逻辑
2. **日志查看**：`nuctl get function my-detector -n nuclio` 查看状态
3. **DRYRUN 模式**：`make deploy FUNCTION=my-detector DRYRUN=true` 预览命令
4. **端口获取**：
   ```bash
   nuctl get function my-detector -n nuclio -o jsonpath='{.status.httpPort}'
   ```

## 示例检测器

参考 `functions/nsfw-detector/` 查看完整实现示例。
