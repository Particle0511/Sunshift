import json
import datetime

class DevOpsHandoff:
    @staticmethod
    def generate_k8s_payload(usual, rec, is_flexible, meta):
        region_map = {
            "Mumbai": "ap-south-1",
            "Hyderabad": "ap-south-2",
            "Delhi NCR": "ap-south-3", 
            "Bengaluru": "ap-south-4",
            "Chennai": "ap-south-5"
        }
        
        cloud_region = region_map.get(rec['region'], "ap-south-1")
        
        payload = {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": f"sunshift-optimized-job-{datetime.datetime.now().strftime('%Y%m%d-%H%M')}",
                "annotations": {
                    "sunshift.io/resume-at": rec['start_time'],
                    "sunshift.io/execution-note": "Job suspended by Sunshift. Target cluster autoscaler (e.g., Karpenter) will provision nodes upon resume.",
                    "sunshift.io/fallback-region": usual['region']
                },
                "labels": {
                    "routed-by": "sunshift-policy-engine",
                    "esg-compliance": "brsr-tracked"
                }
            },
            "spec": {
                "suspend": is_flexible, 
                "template": {
                    "spec": {
                        "nodeSelector": {
                            "topology.kubernetes.io/region": cloud_region,
                            "accelerator": "nvidia-a100"
                        },
                        "containers": [
                            {
                                "name": "ai-training-workload",
                                "image": "enterprise-registry/ai-training:v2",
                                "resources": {
                                    "limits": {
                                        "nvidia.com/gpu": str(meta.get('n_gpus', 48))
                                    }
                                }
                            }
                        ],
                        "restartPolicy": "Never"
                    }
                }
            }
        }
        
        return json.dumps(payload, indent=2)

if __name__ == "__main__":
    mock_usual = {"region": "Mumbai"}
    mock_rec = {"region": "Hyderabad", "start_time": "2026-10-26 10:00"}
    mock_meta = {"n_gpus": 48}
    
    json_output = DevOpsHandoff.generate_k8s_payload(mock_usual, mock_rec, True, mock_meta)
    print(json_output)