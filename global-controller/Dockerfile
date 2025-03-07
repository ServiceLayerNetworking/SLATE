# syntax=docker/dockerfile:1.4
##########################################
## New 
##########################################

# FROM --platform=$BUILDPLATFORM python:3.10-alpine AS builder
FROM python:3.10-slim

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
RUN apt-get install jq -y

RUN rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app
RUN --mount=type=cache,target=/root/.cache/pip \
    pip3 install -r requirements.txt

COPY . /app
COPY ./vimrc_file /root/.vimrc


ENTRYPOINT ["python3"]

CMD ["global_controller.py"]

# CMD ["app.py"]

# EXPOSE 8080


# FROM builder as dev-envs

# RUN <<EOF
# apk update
# apk add git
# EOF

# RUN <<EOF
# addgroup -S docker
# adduser -S --shell /bin/bash --ingroup docker vscode
# EOF
# # install Docker tools (cli, buildx, compose)
# COPY --from=gloursdocker/docker / /


##########################################
## Original global controller Dockerfile #
##########################################
# FROM python:3.10

# WORKDIR /app

# RUN apt-get update
# RUN apt-get install software-properties-common -y
# RUN apt-get install iputils-ping -y
# RUN apt-get install wget -y
# RUN apt-get install curl -y
# # RUN apt-get install python3-pip -y
# RUN apt-get install vim -y
# RUN apt-get install procps -y
# RUN apt-get install htop -y

# COPY requirements.txt ./
# RUN pip install -r requirements.txt

# COPY *.py .
# # COPY new_trace.txt .
# # COPY trace-west_only-avg_load.csv .
# # COPY wrk_prof_log2_west.txt .
# # COPY wrk_prof_log2_east.txt .
# # COPY wrk_prof_log2_both_cluster.txt .
# COPY sampled_west_trace.txt .
# COPY sampled_both_trace.txt .
# # COPY config.json .

# CMD ["python3", "global_controller.py"]

# EXPOSE 8080