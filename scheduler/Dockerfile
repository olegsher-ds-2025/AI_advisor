FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY scheduler/requirements.txt scheduler/requirements.txt
RUN pip install --no-cache-dir -r scheduler/requirements.txt
COPY . .
ENTRYPOINT ["python", "-u", "-m", "scheduler.jobs"]
