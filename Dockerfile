FROM python:3.10-slim

ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

RUN sed -i "s@http://deb.debian.org@https://mirrors.tuna.tsinghua.edu.cn@g" /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y wget \
    && apt-get install -y python3 python3-pip python-dev build-essential python3-venv \
    && python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --upgrade pip \
    && pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && mkdir -p /app

ADD . /app
WORKDIR /app

RUN pip3 install -r requirements.txt

CMD ["python", "bot/bot.py"]