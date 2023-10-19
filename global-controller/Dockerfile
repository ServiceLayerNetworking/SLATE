FROM python:3.10

WORKDIR /app

RUN apt-get update
RUN apt-get install software-properties-common -y
RUN apt-get install iputils-ping -y
RUN apt-get install wget -y
RUN apt-get install curl -y
# RUN apt-get install python3-pip -y
RUN apt-get install vim -y
RUN apt-get install procps -y
RUN apt-get install htop -y

COPY gurobi.lic ./
# Gurobi bin for grbgetkey binary
# RUN wget https://packages.gurobi.com/lictools/licensetools10.0.2_linux64.tar.gz
# Gurobi license
# RUN gurobi1003/linux64/bin/grbgetkey 9ad8f131-3be3-4cfe-98de-32ddcf1c296b

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY *.py .
COPY new_trace.txt .
COPY trace-west_only-avg_load.csv .
# COPY config.json .

CMD ["python3", "global_controller.py"]

EXPOSE 8080
