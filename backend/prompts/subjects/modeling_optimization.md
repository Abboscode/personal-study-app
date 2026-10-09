Modeling and Optimization of Embedded Systems

Prioritize reasoning about embedded-system models, languages, synthesis, scheduling, verification, optimization, and performance.

Important topics may include:

SystemC;

SC_MODULE;

SC_CTOR;

ports and signals;

modules and hierarchy;

SC_METHOD;

SC_THREAD;

SC_CTHREAD;

static and dynamic sensitivity;

events;

wait();

clocks;

resets;

delta cycles;

SystemC simulation semantics;

concurrency;

signal update semantics;

RTL modeling;

Transaction-Level Modeling;

hardware/software co-design;

High-Level Synthesis;

Kahn Process Networks;

dataflow networks;

determinacy;

schedulability;

static scheduling;

token production and consumption;

buffer requirements;

code-size optimization;

memory-size optimization;

Extended Finite State Machines;

Moore and Mealy models;

synchronous composition;

StateCharts;

Esterel;

ECL;

emit;

await;

abort;

parallel composition;

synchronous-language synthesis;

formal verification;

Worst-Case Execution Time;

software performance analysis;

computational and communication requirements;

hardware/software architecture selection.

Only prioritize topics actually present in the current slides.

SystemC

SystemC is especially important.

When supported by the slides, generate enough "code" and "problem" questions that the student becomes capable of reconstructing important SystemC templates during the exam.

Questions should test whether the student can:

understand SystemC code;

predict execution;

explain execution semantics;

reconstruct important code;

modify code for related requirements;

trace processes over time;

reason about sensitivity lists;

determine when processes execute;

distinguish simulation time from delta cycles;

reason about signal updates;

analyze concurrent processes;

identify synchronization problems;

translate requirements into SystemC modules/processes;

model RTL behavior;

compare RTL and TLM.

Follow the professor's SystemC syntax and examples.

Do not replace them with generic templates if the slides use another form.

Dataflow / KPN

When supported, ask the student to:

identify processes/actors;

identify channels;

determine token rates;

trace firing sequences;

reason about determinacy;

determine schedulability;

construct static schedules;

calculate repetition counts;

calculate buffer requirements;

identify deadlock situations;

compare schedules;

optimize code size;

optimize memory usage.

If a worked scheduling example appears, generate at least one problem requiring the reasoning to be reconstructed.

EFSM / Synchronous Languages

When supported, prioritize:

state/output tracing;

Moore vs Mealy reasoning;

EFSM construction;

synchronous composition;

parallel behavior;

emit;

await;

abort;

logical instants;

Esterel/ECL execution;

synthesis consequences.

Performance / WCET

When formulas or performance methods are present:

generate calculations;

require intermediate steps;

preserve professor notation;

state assumptions carefully;

test both calculation and interpretation.

When supported, test understanding of:

average vs worst-case execution time;

simulation-based WCET;

static/formal WCET;

path analysis;

hardware effects on execution time.

Do not introduce WCET claims that are not present in the supplied slides.