FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# iztro runtime for charting
COPY package.json /app/
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm && \
    npm install --omit=dev && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY . /app

EXPOSE 8787
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8787"]
