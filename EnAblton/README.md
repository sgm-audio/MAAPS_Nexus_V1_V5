# EnAblton - Advanced Ableton Live Integration Suite

## Real-time Audio Processing & MIDI Control System

**Production-ready C++/Rust Integration for Max for Live, JUCE, and ONNX-powered Audio Processing**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          EnAblton V1-V5 Stack                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  V5: API Gateway Layer (Traefik/Kong Integration)                           │
│  V4: Distributed Audio Processing (Rust ONNX Workers)                       │
│  V3: Real-time DSP Chain (JUCE Plugin Framework)                            │
│  V2: MIDI Mapping Engine (Max for Live Integration)                         │
│  V1: Core Infrastructure (Audio/MIDI I/O Management)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                     Core Components                                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │Max for  │ │ JUCE    │ │ Rust    │ │ ONNX    │ │ Ableton │ │ IPC     │   │
│  │Live SDK  │ │Plugin  │ │Audio    │ │Inference│ │Link    │ │Layer    │   │
│  │         │ │Framework│ │Processing│ │Engine   │ │Sync    │ │         │   │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Project Scope

### V1: Core Infrastructure (Audio/MIDI I/O Management)
- Real-time audio buffer management
- Low-latency MIDI input/output handling
- Inter-process communication layer
- Performance monitoring and diagnostics

### V2: MIDI Mapping Engine (Max for Live Integration)
- Max for Live device integration
- Dynamic MIDI control surface mapping
- Custom parameter automation
- Device state synchronization

### V3: Real-time DSP Chain (JUCE Plugin Framework)
- JUCE-based plugin architecture
- Memory-safe audio processing
- Sample-accurate timing
- Plugin hosting capabilities

### V4: Distributed Audio Processing (Rust ONNX Workers)
- Rust-based memory-safe audio processing
- ONNX model inference for audio analysis
- Parallel processing capabilities
- GPU acceleration support

### V5: API Gateway Layer (Traefik/Kong Integration)
- RESTful API for DAW control
- WebSockets for real-time updates
- Authentication and authorization
- Rate limiting and monitoring

---

## Engineering Methodologies

This project strictly adheres to Level 5 Engineering/Agile/XP methodologies:

### Engineering Excellence
- Test-driven development (TDD)
- Continuous integration/deployment (CI/CD)
- Code reviews and pair programming
- Automated testing and quality gates

### Agile Practices
- Iterative development cycles
- Daily standups and retrospectives
- User story-driven development
- Continuous feedback loops

### XP Principles
- Simple design and refactoring
- Collective code ownership
- Sustainable pace of work
- On-site customer collaboration

---

## Technical Specifications

### C++ Components (Max for Live/JUCE)
- Max SDK integration for Max for Live devices
- JUCE framework for cross-platform plugins
- Real-time safe audio processing
- Memory management optimization

### Rust Components (ONNX Inference/Audio Processing)
- Memory-safe audio processing pipeline
- ONNX runtime for AI model inference
- Concurrency with async/await patterns
- Zero-cost abstractions

### Key Features
- Optimized real-time audio handling
- MIDI control mapping system
- Ableton Link support for synchronization
- Inter-process communication
- Production-ready performance monitoring
- Seamless DAW integration

---

## Getting Started

```bash
# Clone and enter the project
cd EnAblton

# Initialize submodules
git submodule update --init --recursive

# Build C++ components
cd cpp && make build

# Build Rust components
cd rust && cargo build --release

# Start the system
./enabltion start
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Max for Live Integration** | Cycling74 Max SDK |
| **Audio Plugins** | JUCE Framework |
| **Audio Processing** | Rust (memory-safe) |
| **AI Inference** | ONNX Runtime |
| **MIDI Control** | Native APIs (Windows/macOS/Linux) |
| **Synchronization** | Ableton Link Protocol |
| **IPC** | Shared memory, sockets |

---

## License

Proprietary License - All Rights Reserved by Scott G Mills and SGM Studios.