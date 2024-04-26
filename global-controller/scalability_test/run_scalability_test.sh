# num_cluster=2
# num_callgraph=2
# depth=3
# fanout=2
# python global_controller.py ${num_clustert} ${num_callgraph} ${depth} ${fanout}
output_fn="result.csv"
echo "title,num_cluster,num_callgraph,depth,fanout,num_svc,num_endpoint,degree,solver_time" > ${output_fn}
for depth in {2..10}
do
    for num_callgraph in {2..8}
    do
        for num_cluster in {2..10}
        do
            for fanout in {1..1}
            do
                for degree in {1..1}
                do
                    # python global_controller.py ${num_cluster} ${num_callgraph} ${depth} ${fanout} ${degree} | grep solver_time >> ${output_fn}
                    python global_controller.py ${num_cluster} ${num_callgraph} ${depth} ${fanout} ${degree} >> ${output_fn}
                done
            done
        done
    done
done