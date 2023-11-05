cluster=$1
rps=$2
duration=$3

if [ ${cluster} == "us-west" ]
then
    addr="http://172.18.255.200:80/productpage"
elif [ ${cluster} == "us-east" ]
then
    addr="http://172.18.245.200:80/productpage"
else
    echo "Invalid cluster name: ${cluster}"
    echo "exit shell..."
    exit
fi

#echo "[SLATE], ===================================================="
#echo "[SLATE], cluster,${cluster},addr,${addr},rps,${rps},duration,${duration}"
echo "*******************"
echo "** Cluster: ${cluster}"
echo "** RPS: ${rps}"
echo "** Duration: ${duration}s"
echo "*******************"
#./hey_linux_amd64 -z ${duration}s -c ${cc} ${addr}
#./wrk -t5 -c20 -d${duration}s -R${rps} -r -D "fixed" ${addr}
./wrk -t5 -c50 -d${duration}s -R${rps} -D "exp" ${addr}
#echo "[SLATE], Done"
#echo "[SLATE], ===================================================="
#echo 
