FROM python:3.10-slim

ENV PYTHONFAULTHANDLER=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONHASHSEED=random
ENV PYTHONDONTWRITEBYTECODE 1
ENV PIP_NO_CACHE_DIR=off
ENV PIP_DISABLE_PIP_VERSION_CHECK=on
ENV PIP_DEFAULT_TIMEOUT=100

RUN sed -i "s@http://deb.debian.org@https://mirrors.tuna.tsinghua.edu.cn@g" /etc/apt/sources.list
RUN apt-get update
RUN apt-get install -y ca-certificates wget
RUN apt-get install -y python3 python3-pip python-dev build-essential python3-venv

#COPY config/telegram.crt /usr/local/share/ca-certificates/
#RUN update-ca-certificates


RUN python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --upgrade pip
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

#RUN pip install certifi
#RUN python -m certifi
#RUN wget https://developers.cloudflare.com/cloudflare-one/static/documentation/connections/Cloudflare_CA.pem
#RUN echo | cat - Cloudflare_CA.pem >> $(python -m certifi)
#
#RUN export CERT_PATH=$(python -m certifi)
#RUN export SSL_CERT_FILE=${CERT_PATH}
#RUN export REQUESTS_CA_BUNDLE=${CERT_PATH}

RUN mkdir -p /app
ADD . /app
WORKDIR /app

RUN pip3 install -r requirements.txt

CMD ["python", "bot/bot.py"]