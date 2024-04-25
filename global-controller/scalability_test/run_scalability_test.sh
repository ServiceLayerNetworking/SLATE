# num_cluster=2
# num_callgraph=2
# depth=3
# fanout=2
# python global_controller.py ${num_clustert} ${num_callgraph} ${depth} ${fanout}

for depth in {2..10}
do
    for num_callgraph in {4..4}
    do
        for num_cluster in {2..50}
        do
            for fanout in {2..2}
            do
                for degree in {1..2}
                do
                    python global_controller.py ${num_cluster} ${num_callgraph} ${depth} ${fanout} ${degree} >> result.csv
                done
            done
        done
    done
done