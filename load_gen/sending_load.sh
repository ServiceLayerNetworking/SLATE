#cluster=$1
rps=$1
duration=$2

ip_file=ip.txt
while IFS= read -r line; do
    lines+=("$line")
    done < ${ip_file}

for line in "${lines[@]}"; do
    echo "$line"
done

#if [ ${cluster} == "us-west" ]
#then
#    addr="http://198.22.255.4/productpage"
#elif [ ${cluster} == "us-east" ]
#then
#    addr="http://172.18.245.200:80/productpage"
#else
#    echo "Invalid cluster name: ${cluster}"
#    echo "exit shell..."
#    exit
#fi

for line in "${lines[@]}"; do
    echo "*******************"
    echo "** Cluster: ${line}"
    echo "** RPS: ${rps}"
    echo "** Duration: ${duration}s"
    echo "*******************"
    ./wrk -t10 -c50 -d${duration}s -R${rps} -D "exp" http://${line}/productpage
done
