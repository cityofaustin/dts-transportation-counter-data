FROM --platform=$BUILDPLATFORM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY active-transportation-counters/ ./active-transportation-counters/

ENTRYPOINT ["python"]
CMD ["active-transportation-counters/get_eco_counter_data.py"]
