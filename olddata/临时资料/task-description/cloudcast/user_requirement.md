# Multi-Cloud Data Multicasting Cost Optimization

Modern cloud-native applications increasingly operate across multiple cloud providers such as AWS, Azure, and GCP. In many real-world scenarios, a source region must distribute the same dataset to multiple destination regions spanning different providers and geographic locations.

Unlike traditional multicast systems, multi-cloud environments introduce heterogeneous **egress costs**. Transferring data across regions or cloud providers incurs monetary charges that vary significantly depending on the network path. As a result, the structure of the multicast topology has a direct impact on the overall cost of data movement.

Each problem instance consists of:

* A **source node** containing the original data
* A set of **destination nodes** that must receive the data
* A directed multi-cloud network graph
* Link-specific transfer costs and throughput capacities
* A fixed number of independent data partitions (stripes)

The objective is to construct a multicast topology that delivers all data partitions from the source to every destination while minimizing total egress cost.

## The Cost Optimization Challenge

A naïve strategy sends data independently from the source to each destination. While simple and reliable, this approach repeatedly pays for expensive inter-cloud transfers and fails to exploit opportunities for sharing network resources.

A more effective multicast strategy can reuse intermediate transfers by routing data through carefully selected relay regions. Multiple destinations may then share the same upstream transmission, reducing redundant traffic over costly network links.

The total multicast cost can be expressed as:

```text
Cost(P) = Σ cost(path_s)
```

where:

* **P** denotes the multicast topology
* **path_s** denotes the transfer path used by partition (stripe) s
* **cost(path_s)** is the total egress cost incurred along that path

Lower cost indicates a more efficient multicast topology.

## Optimization Objective

The goal is to minimize the total egress cost required to deliver data from the source to all destinations:

```text
minimize Total_Egress_Cost
```

An effective algorithm should:

* Reuse shared transfer paths whenever possible
* Reduce the number of expensive inter-cloud transfers
* Exploit low-cost intermediate relay regions
* Construct efficient multicast trees rather than independent routes

## Success Metrics

A successful multicast algorithm should achieve:

1. **Low Cost**: Minimize total egress cost across all benchmark configurations
2. **Feasibility**: Successfully deliver data to every destination node
3. **Robustness**: Perform consistently across different cloud topologies
4. **Efficiency**: Generate multicast topologies within practical runtime limits

The ultimate goal is to discover cost-efficient multicast structures that significantly outperform direct destination-by-destination replication while remaining reliable across diverse multi-cloud environments.
