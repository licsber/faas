# NSFW Detector - 预构建镜像
# 镜像: licsber/nsfw-detector

# 阶段1：模型下载器
FROM python:3.12-slim AS model-downloader

ENV HF_HOME=/opt/huggingface
ENV TRANSFORMERS_CACHE=/opt/huggingface/models
ENV HF_HUB_ENABLE_HF_TRANSFER=1

RUN pip install --no-cache-dir torch torchvision transformers huggingface-hub pillow

RUN python3 << 'EOF'
from transformers import AutoModelForImageClassification, AutoImageProcessor
model_name = 'Falconsai/nsfw_image_detection'
print(f'Downloading: {model_name}')
processor = AutoImageProcessor.from_pretrained(model_name, cache_dir='/opt/huggingface/models')
model = AutoModelForImageClassification.from_pretrained(model_name, cache_dir='/opt/huggingface/models')
print('Model downloaded')
EOF

# 阶段2：最终镜像
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

RUN pip install --no-cache-dir torch torchvision transformers Pillow numpy requests

COPY --from=model-downloader /opt/huggingface /opt/huggingface

ENV HF_HOME=/opt/huggingface
ENV TRANSFORMERS_CACHE=/opt/huggingface/models
ENV PYTHONUNBUFFERED=1
ENV OMP_NUM_THREADS=1
ENV MKL_NUM_THREADS=1
ENV OPENBLAS_NUM_THREADS=1

RUN mkdir -p /opt/nuclio
COPY main.py /opt/nuclio/

WORKDIR /opt/nuclio

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import sys; sys.exit(0)"

EXPOSE 8080
CMD ["python3", "-c", "print('NSFW Detector ready')"]
