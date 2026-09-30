import re
import pandas as pd
import numpy as np
from typing import List, Dict

class MobilityLoadBalancer:
    """
    Autonomous Mobility Load Balancing (MLB) & Traffic Steering Engine.
    Matches congested donor cells with high-headroom acceptor neighbors within the same cluster.
    Prescribes 3GPP TS 36.331 compliant Cell Individual Offset (CIO) parameter shifts.
    """
    
    @staticmethod
    def extract_cluster_id(orig_id: str) -> str:
        """Extracts geographic cluster prefix from base station nomenclature."""
        m = re.match(r"^([A-Za-z]+)", str(orig_id))
        return m.group(1).upper() if m else "OTHER"

    def match_traffic_offloads(self, scored_df: pd.DataFrame, mapping_df: pd.DataFrame) -> pd.DataFrame:
        """
        Executes date-synchronized neighbor search with dynamic headroom conservation.
        """
        mapping = mapping_df.copy()
        mapping['Cluster'] = mapping['Original_ERBS_Id'].apply(self.extract_cluster_id)
        
        df = scored_df.merge(
            mapping[['New_ERBS_Id', 'Original_ERBS_Id', 'Cluster']], 
            left_on='ERBS Id', right_on='New_ERBS_Id', how='left'
        )
        
        recommendations = []
        grouped_by_date = df.groupby('Date')
        
        for date, day_df in grouped_by_date:
            donors = day_df[day_df['Congestion_Category'].isin(['CRITICAL', 'HIGH'])].sort_values(
                by=['Congestion_Risk_Score', 'E-UTRAN IP Throughput UE DL (Predicted)'],
                ascending=[False, True]
            )
            
            acceptor_pool = day_df[
                (day_df['Congestion_Category'].isin(['NORMAL', 'MODERATE'])) &
                (day_df['Load_Factor'] < 0.70) &
                (day_df['Headroom'] >= 5.0) &
                (day_df['E-UTRAN IP Throughput UE DL (Predicted)'] >= 8.0) &
                (day_df['4G Cell Av. (%) (Predicted)'] >= 95.0)
            ].copy()
            
            # Dynamic headroom tracker to avoid secondary congestion
            dynamic_headroom = dict(zip(acceptor_pool['ERBS Id'], acceptor_pool['Headroom']))
            
            for _, donor in donors.iterrows():
                cluster = donor['Cluster']
                donor_id = donor['ERBS Id']
                
                # Find available neighbors in the same operational cluster
                cluster_cands = acceptor_pool[
                    (acceptor_pool['Cluster'] == cluster) & 
                    (acceptor_pool['ERBS Id'] != donor_id)
                ].copy()
                
                valid_cands = [c for _, c in cluster_cands.iterrows() if dynamic_headroom.get(c['ERBS Id'], 0) >= 4.0]
                if not valid_cands:
                    continue
                    
                cand_df = pd.DataFrame(valid_cands)
                cand_df['Score'] = cand_df['ERBS Id'].map(dynamic_headroom) * cand_df['E-UTRAN IP Throughput UE DL (Predicted)']
                best_acc = cand_df.sort_values(by='Score', ascending=False).iloc[0]
                acc_id = best_acc['ERBS Id']
                
                # Compute user transfer volume
                donor_users = donor['Avg RRC Connected users (Predicted)']
                acc_headroom = dynamic_headroom[acc_id]
                shift_users = int(min(donor_users * 0.25, acc_headroom * 0.40))
                shift_users = max(shift_users, 3)
                
                dynamic_headroom[acc_id] -= shift_users
                
                # 3GPP CIO Prescription
                if shift_users >= 10:
                    cio_action = "+3 dB Handover Offset"
                    priority = "HIGH"
                elif shift_users >= 6:
                    cio_action = "+2 dB Handover Offset"
                    priority = "MEDIUM"
                else:
                    cio_action = "+1 dB Handover Offset"
                    priority = "LOW"
                    
                cur_speed = donor['E-UTRAN IP Throughput UE DL (Predicted)']
                est_speed = round(cur_speed * (donor_users / max(donor_users - shift_users, 1)), 2)
                qoe_boost = round(((est_speed - cur_speed) / cur_speed) * 100, 1)
                
                recommendations.append({
                    'Date': date,
                    'Cluster': cluster,
                    'Priority': priority,
                    'Congestion_Severity': donor['Congestion_Category'],
                    'Risk_Score': donor['Congestion_Risk_Score'],
                    'Donor_Tower_Id': donor_id,
                    'Donor_Original_Name': donor['Original_ERBS_Id'],
                    'Donor_Current_Users': round(donor_users, 1),
                    'Donor_Current_Speed_Mbps': round(cur_speed, 2),
                    'Acceptor_Tower_Id': acc_id,
                    'Acceptor_Original_Name': best_acc['Original_ERBS_Id'],
                    'Acceptor_Initial_Speed_Mbps': round(best_acc['E-UTRAN IP Throughput UE DL (Predicted)'], 2),
                    'Acceptor_Initial_Headroom': round(best_acc['Headroom'], 1),
                    'Users_To_Offload': shift_users,
                    'Recommended_3GPP_Action': f"Configure Cell Individual Offset (CIO) {cio_action} towards {acc_id}",
                    'Estimated_Donor_Speed_After': est_speed,
                    'Predicted_QoE_Boost': f"+{qoe_boost}%"
                })
                
        return pd.DataFrame(recommendations)
