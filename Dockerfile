FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8098

VOLUME ["/config", "/data", "/media", "/logs"]

ENV TZ=Asia/Shanghai

LABEL net.unraid.docker.managed="dockerman" \
      net.unraid.docker.webui="http://[IP]:[PORT:8098]" \
      net.unraid.docker.icon="https://lf-fe.fqnovelstatic.com/obj/novel-fanqie-fe/growth/incentive-h5-monorepo/apps/hongguo/app-logo.png"

ENTRYPOINT ["python", "-m", "HGDJ.cli"]
CMD ["--config", "/config/config.json", "--daemon"]
