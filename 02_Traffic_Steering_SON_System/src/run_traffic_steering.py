import os
import pandas as pd
from congestion_detector import CongestionDetector
from mobility_load_balancer import MobilityLoadBalancer

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SRC_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")
OUTPUTS_DIR = os.path.join(PROJECT_DIR, "outputs")

def main():
    print("=" * 70)
    print("AI Traffic Steering & Mobility Load Balancing (MLB) Pipeline")
    print("=" * 70)
    
    # 1. Load Data
    clean_path = os.path.join(DATA_DIR, "Data_Cleaned.csv")
    preds_path = os.path.join(DATA_DIR, "tower_level_forecast_predictions.csv")
    mapping_path = os.path.join(DATA_DIR, "tower_mapping.csv")
    
    clean_df = pd.read_csv(clean_path)
    preds_df = pd.read_csv(preds_path)
    mapping_df = pd.read_csv(mapping_path)
    
    # 2. Congestion Detection
    detector = CongestionDetector()
    capacity_df = detector.fit_capacity_ceilings(clean_df)
    scored_df = detector.calculate_congestion_scores(preds_df, capacity_df)
    
    alerts_df = scored_df[scored_df['Congestion_Category'].isin(['CRITICAL', 'HIGH'])].copy()
    alerts_path = os.path.join(OUTPUTS_DIR, "congestion_alerts_summary.csv")
    alerts_df.to_csv(alerts_path, index=False)
    print(f"\n>>> Total Congestion Alerts Detected: {len(alerts_df):,}")
    print(scored_df['Congestion_Category'].value_counts())
    
    # 3. Mobility Load Balancing
    balancer = MobilityLoadBalancer()
    recs_df = balancer.match_traffic_offloads(scored_df, mapping_df)
    recs_path = os.path.join(OUTPUTS_DIR, "traffic_steering_recommendations.csv")
    recs_df.to_csv(recs_path, index=False)
    print(f"\n>>> Total Actionable 3GPP Recommendations Generated: {len(recs_df):,}")
    print(recs_df['Priority'].value_counts())
    
    # 4. Regional Cluster Capacity Breakdown
    scored_df['Cluster'] = scored_df['ERBS Id'].map(
        dict(zip(mapping_df['New_ERBS_Id'], mapping_df['Original_ERBS_Id'].apply(balancer.extract_cluster_id)))
    )
    cluster_summary = scored_df.groupby('Cluster').agg({
        'ERBS Id': 'nunique',
        'Avg RRC Connected users (Predicted)': ['mean', 'max'],
        'E-UTRAN IP Throughput UE DL (Predicted)': 'mean',
        'Congestion_Risk_Score': 'mean',
        'Headroom': 'sum'
    }).round(2)
    cluster_summary.columns = ['Total_Towers', 'Avg_Users_Per_Tower', 'Peak_Tower_Users', 'Avg_Speed_Mbps', 'Avg_Congestion_Risk', 'Total_Cluster_Headroom']
    cluster_path = os.path.join(OUTPUTS_DIR, "cluster_capacity_breakdown.csv")
    cluster_summary.to_csv(cluster_path)
    print(f"\n>>> Saved Cluster Breakdown to: {cluster_path}")
    
    print("\n>>> Sample Prescriptions:")
    print(recs_df[['Date', 'Cluster', 'Priority', 'Donor_Tower_Id', 'Users_To_Offload', 'Recommended_3GPP_Action', 'Predicted_QoE_Boost']].head(5).to_string(index=False))

if __name__ == '__main__':
    main()
