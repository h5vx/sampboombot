FROM python:3.12-alpine

COPY . /sampboombot
WORKDIR /sampboombot

ENV PYTHONDONTWRITEBYTECODE=abc

RUN apk update && \
    apk add libshout libshout-dev gcc musl-dev && \
    pip install --no-cache -r requirements.txt && \
    apk del libshout-dev gcc musl-dev && \
    apk cache clean && \
    rm -rf /var/cache/apk /root/.cache

CMD ["python", "/sampboombot/main.py"]