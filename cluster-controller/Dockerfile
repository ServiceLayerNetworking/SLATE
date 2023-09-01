FROM golang:1.20-alpine
RUN mkdir /app
ADD . /app/
WORKDIR /app
RUN go build -o main .
CMD ["/app/main"]

EXPOSE 8080