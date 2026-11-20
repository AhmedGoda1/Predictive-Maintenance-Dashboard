\# AI-Based Predictive Maintenance Dashboard for Milling Machines

## 🚀 Live Dashboard

🔗 **[Open Live Streamlit Dashboard](https://rvmr18-milling-machine-predictive-maintenance-app-y4vpab.streamlit.app/)**

An experimental predictive maintenance system that uses milling machine sensor data, statistical signal processing, and machine learning to estimate cutting tool flank wear and support maintenance decision-making.



\*\*Technologies:\*\* Python | Streamlit | NumPy | Pandas | SciPy | Scikit-learn | Plotly | SQLite



\## 1. Project Overview



This project investigates the application of sensor signal analysis and machine learning for predictive maintenance in milling operations.



The main objective is to estimate cutting tool flank wear (VB) using sensor measurements collected during milling experiments. The project combines experimental data preparation, statistical feature extraction, machine-learning model development, model evaluation, and an interactive maintenance dashboard.



The system also demonstrates how experimental results can be connected to maintenance activities through alert monitoring and work-order management.



\## 2. Project Objectives



\- Analyse sensor measurements collected during milling operations.

\- Extract statistical features from vibration, current, and acoustic emission signals.

\- Develop a machine-learning regression model to estimate tool flank wear.

\- Evaluate model performance using group-based cross-validation.

\- Visualise experimental measurements and model predictions.

\- Implement maintenance alerts and work-order management.

\- Present the results through an interactive dashboard.



\## 3. Dataset and Experimental Data Preparation



The project uses the NASA Milling Wear Dataset, which contains measurements from milling experiments.



The dataset includes experimental information such as:



\- Case and run identifiers

\- Tool flank wear (VB)

\- Experiment time

\- Depth of cut (DOC)

\- Feed rate

\- Material information



Six sensor signals were used for feature extraction:



| Signal | Description |

|---|---|

| `smcAC` | AC spindle motor current |

| `smcDC` | DC spindle motor current |

| `vib\_table` | Table vibration |

| `vib\_spindle` | Spindle vibration |

| `AE\_table` | Table acoustic emission |

| `AE\_spindle` | Spindle acoustic emission |



\### Data preparation process



The original MATLAB dataset was processed to prepare the experimental measurements for analysis.



\- Initial experimental runs: 167

\- Runs excluded due to missing VB labels: 21

\- Additional experiment excluded due to corrupted sensor values: Experiment 18

\- Final labelled experimental runs used: 145



The processed feature dataset is included in:



`database/milling\_features.csv`



The original dataset is available from the NASA Open Data source referenced in the acknowledgement section.



\## 4. Signal Processing and Feature Engineering



Statistical features were extracted from each of the six sensor signals.



Ten features were calculated for each signal:



1\. Mean

2\. Standard deviation

3\. Root Mean Square (RMS)

4\. Peak-to-Peak

5\. Maximum

6\. Minimum

7\. Crest Factor

8\. Kurtosis

9\. Skewness

10\. Energy



This produced:



\*\*6 sensor signals × 10 statistical features = 60 features per experimental run.\*\*



The extracted features represent different characteristics of the sensor signals and are used as inputs for the machine-learning model.



The feature engineering implementation is available in:



`modules/feature\_engineering.py`



\## 5. Machine-Learning Model Development



A Random Forest Regression model was developed to estimate cutting tool flank wear (VB).



\### Model configuration



| Parameter | Value |

|---|---:|

| Algorithm | Random Forest Regressor |

| Number of estimators | 150 |

| Maximum depth | 8 |

| Minimum samples per leaf | 2 |

| Maximum features | 0.8 |

| Random state | 42 |

| Number of jobs | -1 |



\### Model validation



A five-fold GroupKFold cross-validation strategy was used.



The experiments were grouped by their case identifiers. This approach helps prevent experiments belonging to the same case from being placed in both training and validation sets within an individual fold.



A median Dummy Regressor was used as a baseline to compare the Random Forest model against a simple reference prediction.



The model implementation and prediction functions are available in:



`modules/prediction.py`



\## 6. Experimental Model Evaluation



The following results were obtained during the model evaluation.



| Metric | Random Forest | Median Baseline |

|---|---:|---:|

| MAE | 0.1324 | 0.1966 |

| RMSE | 0.1985 | 0.2694 |

| R² | 0.4152 | -0.0766 |



\### Performance comparison



Compared with the median baseline, the Random Forest model achieved:



\- 32.6% lower Mean Absolute Error (MAE).

\- 26.3% lower Root Mean Squared Error (RMSE).

\- A positive R² score of 0.4152.



These results suggest that the extracted sensor features contain useful information for estimating cutting tool wear.



However, the prediction performance still has limitations. The results should be considered experimental and do not demonstrate production-ready predictive maintenance performance.



The trained model is stored in:



`models/milling\_wear\_model.joblib`



\## 7. Interactive Dashboard



The application was developed using Python and Streamlit. It contains six main sections.



\### 7.1 Overview



Provides a summary of the experimental dataset and maintenance information.



Includes:

\- Total experiments

\- Average measured tool wear

\- Open maintenance alerts

\- Active work orders

\- Dataset, model, and database status

\- Recent maintenance alerts and work orders



\### 7.2 Machine Monitoring



Allows users to select and inspect individual experimental runs.



Includes:

\- Sensor signal visualisation

\- Signal statistics

\- Tool wear information

\- Comparisons between experimental cases



\### 7.3 AI Prediction



Provides machine-learning-based tool wear estimation.



Includes:

\- Experiment selection

\- Predicted and measured wear comparison

\- Model evaluation metrics

\- Prediction information and limitations



\*\*Important evaluation note:\*\* The selected labelled experiment comparison shown in the dashboard is an in-sample demonstration. It is not an independent test-set prediction. The GroupKFold cross-validation results provide the more appropriate estimate of model generalisation performance.



\### 7.4 Alert Centre



Provides maintenance alert management based on measured tool wear thresholds.



Includes:

\- Warning and critical alert levels

\- Alert filtering

\- Alert status management

\- Duplicate alert prevention



Alerts are generated from measured VB threshold conditions, not directly from machine-learning predictions.



\### 7.5 Work Orders



Provides basic maintenance task management.



Includes:

\- Creating work orders

\- Assigning technicians

\- Setting task priorities

\- Updating work-order status

\- Saving maintenance records in SQLite



\### 7.6 Lean Analytics



Provides exploratory case-based maintenance analysis.



Includes:

\- Threshold exceedance analysis

\- Pareto chart

\- 80% reference line

\- Work-order status distribution

\- Summary analytics



These visualisations support maintenance analysis but should not be interpreted as proof of actual production losses or failure causes.



\## 8. Database



SQLite is used to store maintenance alerts and work orders.



Database location:



`database/milling.db`



Main application tables:



\- `milling\_alerts`

\- `milling\_work\_orders`



The repository includes demonstration database records so that the maintenance functionality can be explored when running the application.



\## 9. Project Structure



```text

milling-machine-predictive-maintenance/

│

├── app.py

├── README.md

├── requirements.txt

│

├── assets/

│   └── milling\_machine.jpg

│

├── database/

│   ├── milling.db

│   └── milling\_features.csv

│

├── models/

│   └── milling\_wear\_model.joblib

│

├── modules/

│   ├── feature\_engineering.py

│   ├── maintenance\_db.py

│   └── prediction.py

│

└── pages/

&#x20;   ├── ai\_prediction.py

&#x20;   ├── alert\_centre.py

&#x20;   ├── lean\_analytics.py

&#x20;   ├── machine\_monitoring.py

&#x20;   ├── overview.py

&#x20;   └── work\_orders.py

```



\## 10. Installation and Execution



\### Requirements



\- Python 3.10 or later

\- pip

\- Internet connection for installing dependencies



\### Step 1: Clone the repository



```bash

git clone https://github.com/RVMR18/milling-machine-predictive-maintenance.git

cd milling-machine-predictive-maintenance

```



\### Step 2: Install dependencies



```bash

pip install -r requirements.txt

```



\### Step 3: Run the application



```bash

streamlit run app.py

```



\### Step 4: Open the dashboard



\[Open the local dashboard](http://localhost:8501)



The dashboard is available at this address when the Streamlit application is running locally.



A publicly accessible deployed application link will be added after cloud deployment.



\## 11. Limitations and Future Improvements



This project is an experimental engineering prototype and is not intended to replace an industrial predictive maintenance system.



Current limitations:



\- The model uses a limited experimental dataset.

\- Prediction accuracy requires further improvement.

\- Additional independent validation is needed.

\- The dashboard uses recorded experimental data rather than live machine sensor acquisition.

\- Maintenance alerts are based on measured wear thresholds rather than predicted future failures.

\- Persistent storage needs consideration when deploying the SQLite-based application to a cloud environment.



Possible future improvements:



\- Evaluate additional machine-learning algorithms.

\- Improve feature selection and signal analysis.

\- Validate the model using additional independent experiments.

\- Integrate real-time sensor acquisition.

\- Improve maintenance decision-support functionality.

\- Implement persistent cloud database storage.



\## 12. Dataset Acknowledgement



This project uses the NASA Milling Wear Dataset, associated with research involving the University of California, Berkeley Emergent Space Tensegrities (BEST) Laboratory.



Dataset source:



\[NASA Open Data – Milling Wear](https://data.nasa.gov/dataset/milling-wear)



\---



\*\*Project note:\*\* This is an educational and experimental engineering project investigating the use of sensor signal processing and machine learning for predictive maintenance in milling operations.
