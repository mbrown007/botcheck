FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn pydantic openai

COPY services/http-test-bot/ ./

EXPOSE 8080

CMD ["python", "main.py"]
