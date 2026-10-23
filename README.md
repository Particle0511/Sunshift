# Sunshift
**Intelligent AI Workload Placement for Indian Data Centers**

Sunshift is a high-performance optimization engine and executive dashboard built to dynamically schedule and route AI workloads across India's grid infrastructure. By analyzing time-of-day (ToD) tariffs, CEA grid emission factors, and localized WRI water stress indices, Sunshift finds the exact temporal and spatial window to minimize financial cost, carbon footprint, and cooling water consumption.

## Core Features
* **Multi-Dimensional Optimization:** Vectorized physics engine calculates total KWh, INR cost, kg CO2, and cooling water liters across 72-hour forecast windows.
* **Dynamic Time-of-Day Routing:** Automatically shifts flexible workloads into high-solar, low-tariff hours while avoiding evening grid peaks.
* **Environmental Penalty Scoring:** Min-max normalizes trade-offs between water-stressed regions and carbon-heavy grids using user-defined weightings.
* **Executive Bento-Box UI:** Built on Streamlit with custom CSS flexbox architecture, Inria Serif typography, and responsive Plotly comparison charts.
* **100% Test Coverage:** Core logic backed by a robust `pytest` suite ensuring mathematical integrity across edge cases.

## System Architecture
* **`WorkloadOptimizer`**: Handles multi-variable scoring, sliding window analysis, and regional comparisons.
* **`PhysicsEngine`**: NumPy-vectorized module computing PUE scaling, thermal penalties, and baseline resource consumption.
* **`ReasonExplainer`**: Generates human-readable, data-backed narratives explaining the "why" behind every recommendation.
* **`ResultsComparator`**: Calculates absolute and percentage-based delta savings for UI rendering.

## Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/Particle0511/Sunshift.git](https://github.com/Particle0511/Sunshift.git)
   cd Sunshift

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Launch the dashboard:**
   ```bash
   streamlit run app.py
## Testing

Sunshift maintains a strict testing standard. Run the full suite to verify backend integrity:

```bash
pytest   


## License

**MIT License**

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.