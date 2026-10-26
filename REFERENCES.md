# MedNet references and reading guide

These seven references match the literature selected for the project. They support workload generation, simulation methodology, and packet prioritization. They do not establish the numeric packet sizes, rates, deadlines, or weights in MedNet as hospital requirements. Those are synthetic experiment settings.

## Connection to the implementation

| Reference | What to read | Relevant idea | Boundary of the comparison |
|---|---|---|---|
| [1] Botta et al., 2012 | Section 2, Table 2, and Section 4.4 | Specify packet sizes, inter-packet times, and random seeds; use repeatable workloads. | MedNet uses its own Python generator. It does not use D-ITG or inherit its validation. |
| [2] Paxson and Floyd, 1995 | Abstract and Sections III–IV; Sections 3–4 in the author manuscript | Arrival models must distinguish sessions from packets; exponential interarrivals can miss measured burstiness. | These measured TCP traces do not validate or invalidate MedNet's hospital-inspired classes. |
| [3] Floyd and Paxson, 2001 | Section II and Section VI-B | Verify implementation, share experiment settings, and examine sensitivity to parameters. | Results from a configured simulation do not demonstrate operational network performance. |
| [4] Bhandari and Moh, 2016 | Sections 3.2 and 5.1 | Differentiate healthcare traffic; examine performance using modeled packet arrivals. | PA-MAC includes wireless channel access and other mechanisms absent from MedNet. |
| [5] Mazloomi et al., 2023 | Sections 3.1 and 4 | Examine class priority together with elapsed waiting time and congestion. | Their two-queue scheduling, routing, and rate-control system differs from MedNet's score. |
| [6] Asingwire et al., 2023 | Sections 3.1–3.2 and 4 | Consider delay sensitivity, packet size, and effects on lower-priority traffic. | Their heterogeneous multi-server model has infinite queues; MedNet has one finite waiting buffer and one link. |
| [7] Liebeherr et al., 1996 | Abstract and admission-control discussion | Distinguish deadline and priority disciplines and the conditions needed for bounded delay. | MedNet has no admission-control guarantee and its dynamic heuristic is not EDF. |

## Full citations

### [1] Reproducible synthetic workloads

Alessio Botta, Alberto Dainotti, and Antonio Pescapé, “A tool for the generation of realistic network workload for emerging networking scenarios,” *Computer Networks*, vol. 56, no. 15, pp. 3531–3547, 2012. DOI: **10.1016/j.comnet.2012.02.019**.

[Publisher record](https://www.sciencedirect.com/science/article/pii/S1389128612000928) · [Authors' D-ITG bibliography](https://traffic.comics.unina.it/software/ITG/papers.php) · [Full published article, university-hosted copy](https://people.computing.clemson.edu/~jmarty/projects/lowLatencyNetworking/papers/LossandPropModels/AToolForGeneratingRealisticTrafficLoads.pdf)

The paper distinguishes trace-based and statistical model-based generation. Table 2, p. 3533, lists configurable distributions and seeds; Section 4.4, p. 3539, discusses repeatable packet timings. The methodological connection is documentation and repeatability, not use of the D-ITG software.

### [2] Limits of an arrival model

Vern Paxson and Sally Floyd, “Wide area traffic: the failure of Poisson modeling,” *IEEE/ACM Transactions on Networking*, vol. 3, no. 3, pp. 226–244, June 1995. DOI: **10.1109/90.392383**.

[Publisher record](https://ieeexplore.ieee.org/document/392383) · [Author-hosted full paper](https://www.icir.org/vern/papers/poisson.TON.pdf) · [DOI](https://doi.org/10.1109/90.392383)

The authors analyze 24 wide-area traces. Some user-initiated session arrivals fit a Poisson model at fixed hourly rates, while packet-level models can underestimate burstiness. This supports stating MedNet's independent exponential interarrival assumption and avoiding a blanket claim that it reproduces actual hospital traffic. Sections 3–4 occupy pp. 3–5 of the author manuscript; its pagination differs from the journal version.

### [3] Simulation evaluation

Sally Floyd and Vern Paxson, “Difficulties in Simulating the Internet,” *IEEE/ACM Transactions on Networking*, vol. 9, no. 4, pp. 392–403, August 2001. DOI: **10.1109/90.944338**.

[Author publication record](https://www.icir.org/floyd/papers.html) · [Author-hosted full paper](https://www.icir.org/floyd/papers/simulate_2001.pdf) · [DOI](https://doi.org/10.1109/90.944338)

Section II discusses verification and reproducibility. Section VI-B discusses varying parameters and congestion conditions. Section IV-C explains why fixed packet traces cannot reproduce adaptive transport behavior in every new network condition. These distinctions apply to MedNet's fixed synthetic arrivals and parameter experiments.

### [4] Traffic prioritization in a healthcare simulation

Sabin Bhandari and Sangman Moh, “A Priority-Based Adaptive MAC Protocol for Wireless Body Area Networks,” *Sensors*, vol. 16, no. 3, article 401, 2016. DOI: **10.3390/s16030401**.

[Open full paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC4813976/) · [Publisher record](https://www.mdpi.com/1424-8220/16/3/401) · [DOI](https://doi.org/10.3390/s16030401)

The PA-MAC study separates traffic categories and adapts channel access. Section 5.1 uses a Poisson arrival approximation. This is an example of a stated model in healthcare networking research, not evidence that MedNet's specific rates or deadlines are correct. MedNet does not model MAC contention, channels, interference, or energy use.

### [5] Waiting time and congestion

Neda Mazloomi, Majid Gholipour, and Arash Zaretalab, “A priority-based congestion avoidance scheme for healthcare wireless sensor networks,” *IET Wireless Sensor Systems*, vol. 13, no. 1, pp. 9–23, 2023. DOI: **10.1049/wss2.12046**.

[Publisher's open full paper](https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/wss2.12046) · [DOI](https://doi.org/10.1049/wss2.12046)

Section 3.1 combines priority and elapsed waiting time to address lower-priority waiting. The full proposal also includes routing and transmission-rate control, evaluated using NS2 and MATLAB. MedNet borrows the motivation for examining tradeoffs, not this algorithm. The article first appeared online on 19 December 2022; its journal issue is dated 2023.

### [6] Delay and size differentiation

Barbara Kabwiga Asingwire, Louis Sibomana, Alexander Ngenzi, and Charles Kabiri, “Delay and size-dependent priority-aware scheduling for IoT-based healthcare traffic using heterogeneous multi-server priority queueing system,” *IET Communications*, vol. 17, no. 16, pp. 1877–1887, 2023. DOI: **10.1049/cmu2.12675**.

[Publisher's open full paper](https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/cmu2.12675) · [DOI](https://doi.org/10.1049/cmu2.12675)

Sections 3.1–3.2 describe Poisson arrivals, exponential server service times, heterogeneous servers, infinite buffers, and preference based on delay sensitivity and packet size. MedNet's finite single-link simulation differs: serialization time is determined by each packet's size and the configured link rate, and its score has no explicit small-packet preference.

### [7] Deadline service and admission control

Jörg Liebeherr, Dallas E. Wrege, and Domenico Ferrari, “Exact Admission Control for Networks with a Bounded Delay Service,” *IEEE/ACM Transactions on Networking*, vol. 4, no. 6, pp. 885–901, 1996. DOI: **10.1109/90.556345**.

[Author-hosted full paper](https://www.comm.utoronto.ca/~jorg/archive/papers/ton-95-1328.pdf) · [DOI](https://doi.org/10.1109/90.556345)

This paper studies admission control for bounded-delay service under specified traffic and scheduling assumptions. It helps distinguish studying observed deadline outcomes from proving a deadline guarantee. MedNet records late deliveries and buffer drops; it does not implement the paper's admission-control analysis.

## How to explain the project contribution

MedNet implements a documented synthetic packet dataset, a finite-buffer single-link simulator, and a local dashboard for comparing FIFO, fixed priority, and a custom dynamic priority heuristic. Experiments reuse the same packets within each scenario and examine both critical and ordinary traffic. The contribution is the implementation, reproducible experiment, and analysis of tradeoffs. Priority and deadline-aware scheduling are established ideas.

The bibliography contains related methods and evaluation guidance. It is not a claim that the cited authors developed or validated MedNet, nor an exhaustive review of all published work. No paper supplies clinical guarantees for this project.
