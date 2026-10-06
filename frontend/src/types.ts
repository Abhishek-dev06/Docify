export interface Risk {
  score: number | null; category: 'Low'|'Medium'|'High'|null;
  score_range: [number, number]; evidence_coverage: number;
  missing_required_signals: string[]; missing_signals: string[];
  reasons: string[]; policy_version: string; policy_sha256: string;
  contributions: {name:string; points:number; weight:number; complete:boolean; experimental:boolean; explanation:string}[];
}
export interface Layer<T> { status:string; data:T; findings:{code:string; explanation:string; field?:string}[]; duration_ms:number }
export interface Field { raw:string|null; corrected:string|null; confidence:number|null }
export interface Analysis {
  status:string; document_hash:string; duration_ms:number;
  capture:Layer<{image_base64:string; quality:{laplacian_variance:number}}>;
  ocr:Layer<{raw_text:string; mrz:{fields:Record<string,Field>}|null; viz_fields:Record<string,Field>}>|null;
  validation:Layer<{cross_checks:{field:string; consistent:boolean|null}[]}>|null;
  tampering:Layer<{overlay_png_base64:string; cnn_heatmap_png_base64:string|null; detectors:{name:string;status:string;score:number|null;explanation:string}[]}>|null;
  face:Layer<{cosine_similarity:number|null; decision:string}>|null;
  liveness:Layer<{verdict:string}>|null;
  risk:Layer<Risk>;
}
export type Decision = 'approve'|'secondary_inspection'|'reject';
export interface ScanSummary { processing_status:string; document_type:string; risk:Risk; face_similarity:number|null; face_decision:string; duration_ms:number; layer_statuses:Record<string,string>; mismatch_fields:string[] }
export interface AuditEvent<T=ScanSummary> {seq:number;event_id:string;scan_id:string;timestamp:string;actor:string;document_hash:string;event_hash:string;kind:string;payload:T}
export interface DecisionPayload {decision:Decision;note:string;acknowledge_incomplete:boolean}
export interface HistoryItem {scan:AuditEvent;latest_decision:AuditEvent<DecisionPayload>|null;latest_event_hash:string}
export interface Chain {valid:boolean;event_count?:number;head_seq?:number;head_hash?:string;error?:string;failed_seq?:number;limitation?:string}
