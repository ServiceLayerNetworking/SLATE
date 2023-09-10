FROM python:3.10

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY cluster_controller.py .

CMD ["python", "cluster_controller.py"]

EXPOSE 8080
