

output_fn=$1
if [ -z ${output_fn} ]; then
    echo "Usage: $0 <output_fn>"
    exit 1
fi

echo "title,num_cluster,num_request_type,depth,fanout,num_svc,num_endpoint,degree,num_variable,num_constraint,solver_time" > ${output_fn}
for depth in 2 3 4 5 6
do
    # for num_cluster in 2
    for num_cluster in 2 3 4 5 6 7 8 9 10
    do
        for num_callgraph in 1 2 4 6 8 10
        do
            for fanout in 3
            do
                for degree in 1
                do
                    # python global_controller.py ${num_cluster} ${num_callgraph} ${depth} ${fanout} ${degree} | grep solver_time >> ${output_fn}
                    python global_controller.py ${num_cluster} ${num_callgraph} ${depth} ${fanout} ${degree} >> ${output_fn}
                done
            done
        done
    done
done