# Goal
Find older firmware versions for HP OfficeJet Pro 8600 series printers and a HOWTO.md to install them on the device.

# Structure
- `CONCEPT.md`: Defines the goal, core use cases (firmware lookup & installation), and minimal architecture.
- `DESIGN.md`: Technical details for firmware search/retrieval and installation over network (PJL/Socket) or USB.
- `ROADMAP.md`: Steps to implement firmware discovery and installation capabilities.
- `TECHNICAL_DEBTS.md`: Outstanding technical debts or known issues.
- `README.md`: Project overview and usage instructions.
- `/src/`: Source code for firmware discovery and flashing tool.
- `/test/`: Tests and verification scripts.

# `CONCEPT.md` Handling
- Focuses purely on finding existing older firmware and installing it on the target printer.
- Describes the simple workflow: discovery -> firmware payload selection -> printer flashing.

# `DESIGN.md` Handling
- Specifies communication protocols (e.g. PJL over TCP/9100 or USB) for flashing.
- Details mechanisms to locate and download/load compatible legacy firmware files.
