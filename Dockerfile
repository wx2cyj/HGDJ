FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8088

VOLUME ["/config", "/data", "/media", "/logs"]

ENV TZ=Asia/Shanghai

ENTRYPOINT ["python", "-m", "HGDJ.cli"]
CMD ["--config", "/config/config.json", "--daemon"]
