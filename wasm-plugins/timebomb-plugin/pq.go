package main

import (
	"container/heap"
)

// An Item is something we manage in a priority queue.
type PausedRequest struct {
	value    uint32  // value here is the http context id.
	priority uint64    // priority here is time.Now().UnixNano() - requestStartTime
	// The index is needed by update and is maintained by the heap.Interface methods.
	index int // The index of the item in the heap.
}

// A PriorityQueue implements heap.Interface and holds Items.
type RequestPriorityQueue []*PausedRequest

func (pq RequestPriorityQueue) Len() int { return len(pq) }

func (pq RequestPriorityQueue) Less(i, j int) bool {
	// greater because we want to return requests with the most time elapsed first
	return pq[i].priority > pq[j].priority
}

func (pq RequestPriorityQueue) Swap(i, j int) {
	pq[i], pq[j] = pq[j], pq[i]
	pq[i].index = i
	pq[j].index = j
}

func (pq *RequestPriorityQueue) Push(x any) {
	n := len(*pq)
	item := x.(*PausedRequest)
	item.index = n
	*pq = append(*pq, item)
}

func (pq *RequestPriorityQueue) Pop() any {
	old := *pq
	n := len(old)
	item := old[n-1]
	old[n-1] = nil  // avoid memory leak
	item.index = -1 // for safety
	*pq = old[0 : n-1]
	return item
}

// update modifies the priority and value of an Item in the queue.
func (pq *RequestPriorityQueue) update(item *PausedRequest, value uint32, priority uint64) {
	item.value = value
	item.priority = priority
	heap.Fix(pq, item.index)
}