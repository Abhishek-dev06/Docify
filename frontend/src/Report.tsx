import { useRef, useState } from 'react';
import { AlertTriangle, Check, ChevronRight, FileCheck2, ScanFace, ShieldAlert } from 'lucide-react';
import { api, imageUrl, label } from './api';
import type { Analysis, AuditEvent, Decision, DecisionPayload, Risk } from './types';

export function RiskCard({risk}:{risk:Risk}) {
  return <section className="card risk-card"><div className="eyebrow">OBSERVED RISK</div>
    <div className="score-line"><strong>{risk.score === null ? '—' : risk.score.toFixed(2)}</strong><span>/ 100 policy points</span></div>
    <span className={`badge ${risk.category==='High'?'danger':'warning'}`}>{risk.category ? `${risk.category} observed risk` : 'Incomplete evidence'}</span>
    <p className="muted small">Uncalibrated review score. No automatic approval or rejection.</p>
    <div className="coverage"><span>Evidence coverage</span><b>{Math.round(risk.evidence_coverage*100)}%</b></div>
    <div className="progress"><i style={{width:`${risk.evidence_coverage*100}%`}}/></div>
    <p className="small muted">Missing-evidence point range: {risk.score_range[0].toFixed(2)}–{risk.score_range[1].toFixed(2)}. Not a confidence interval.</p>
    {!!risk.missing_required_signals.length && <div className="gap-box"><AlertTriangle size={16}/><div><b>Required evidence is incomplete</b><p>{risk.missing_required_signals.map(label).join(' · ')}</p></div></div>}
  </section>;
}

export default function Report({analysis, event, actor, initialDecision=null, initialHash, onRecorded}:{
  analysis:Analysis|null;event:AuditEvent;actor:string;initialDecision?:AuditEvent<DecisionPayload>|null;initialHash?:string;onRecorded:()=>void;
}) {
  const risk = analysis?.risk.data || event.payload.risk;
  const [view,setView] = useState('capture');
  const [choice,setChoice] = useState<Decision|null>(null);
  const [note,setNote] = useState(''); const [ack,setAck] = useState(false);
  const [saving,setSaving] = useState(false); const [error,setError] = useState('');
  const [latest,setLatest] = useState(initialDecision); const [head,setHead] = useState(initialHash || event.event_hash);
  const [requestId,setRequestId] = useState(crypto.randomUUID());
  const [locked,setLocked] = useState(false);
  const pendingActor = useRef<string|null>(null);
  const incomplete = !!risk.missing_required_signals.length || event.payload.processing_status!=='ok';
  const displayed = analysis && (view==='capture' ? analysis.capture.data.image_base64 : view==='cnn' ? analysis.tampering?.data.cnn_heatmap_png_base64 : analysis.tampering?.data.overlay_png_base64);
  const mismatches = new Set(analysis?.validation?.data.cross_checks.filter(c=>c.consistent===false).map(c=>c.field) || event.payload.mismatch_fields);
  async function decide() {
    if (!choice) return;
    setSaving(true);setLocked(true);setError('');
    pendingActor.current ??= actor;
    try {
      const result = await api<AuditEvent<DecisionPayload>>(`/scans/${event.scan_id}/decisions`, {method:'POST',headers:{'Content-Type':'application/json','X-Officer-ID':pendingActor.current},body:JSON.stringify({decision:choice,note,expected_event_hash:head,request_id:requestId,acknowledge_incomplete:ack})});
      pendingActor.current = null;
      setLatest(result);setHead(result.event_hash);setChoice(null);setNote('');setAck(false);setLocked(false);setRequestId(crypto.randomUUID());onRecorded();
    } catch (e) {setError((e as Error).message+' Retry the same decision, or reopen this scan from History if another decision was recorded.');}
    finally {setSaving(false);}
  }
  return <div className="results" data-testid="report"><div className="section-title"><div><span className="eyebrow">REVIEW WORKSPACE</span><h2>Every signal, in context.</h2></div><span className="badge neutral">Scan {event.scan_id.slice(0,8)}</span></div>
    <div className="review-grid"><div className="review-main">
      <section className="card evidence-card"><div className="card-heading"><h3>Document evidence</h3><span className="small muted">Images stay in this session</span></div>
        {analysis ? <><div className="tabs" role="group" aria-label="Evidence image"><button className={view==='capture'?'active':''} onClick={()=>setView('capture')}>Capture</button><button disabled={!analysis.tampering} className={view==='overlay'?'active':''} onClick={()=>setView('overlay')}>Tamper overlay</button><button disabled={!analysis.tampering?.data.cnn_heatmap_png_base64} className={view==='cnn'?'active':''} onClick={()=>setView('cnn')}>Experimental CNN</button></div><div className="document-stage">{displayed && <img src={imageUrl(displayed)} alt={view==='capture'?'Corrected document':view==='cnn'?'Experimental synthetic CNN heatmap':'Classical tampering overlay'}/>}</div><p className="small muted">{view==='capture'?'Perspective-corrected capture.':view==='cnn'?'Synthetic-only CNN activation; excluded from risk scoring.':'Original-image coordinate frame. Highlighted regions are review signals, not proof of tampering.'}</p></> : <div className="empty-small"><FileCheck2/><h4>Images were not retained</h4><p>History stores scores and review metadata. Extracted identity fields and images are excluded.</p></div>}
      </section>
      <section className="card"><div className="card-heading"><h3>Extracted fields</h3><span className="badge neutral">{mismatches.size} mismatches</span></div>
        {analysis?.ocr ? <div className="table-wrap"><table><thead><tr><th>Field</th><th>MRZ</th><th>Printed / VIZ</th></tr></thead><tbody>{['name','number','nationality','dob','expiry','gender'].map(field=><tr key={field} className={mismatches.has(field)?'mismatch':''}><th>{label(field)}{mismatches.has(field)&&<span className="mismatch-label">Mismatch</span>}</th>{[analysis.ocr!.data.mrz?.fields[field],analysis.ocr!.data.viz_fields[field]].map((v,i)=><td key={i}><span>{v?.corrected || 'Not extracted'}</span>{v?.raw&&v.raw!==v.corrected&&<small>Raw: {v.raw}</small>}{v?.confidence!=null&&<small>OCR confidence {Math.round(v.confidence*100)}%</small>}</td>)}</tr>)}</tbody></table></div> : <p className="muted">No retained field values. {mismatches.size ? `Mismatch fields: ${[...mismatches].map(label).join(', ')}` : 'No comparison available here.'}</p>}
        {analysis?.ocr && <details><summary>Raw OCR and extraction notes</summary><pre>{analysis.ocr.data.raw_text}</pre>{analysis.ocr.findings.map((f,i)=><p className="small" key={i}>{f.explanation}</p>)}</details>}
      </section>
      <section className="card"><div className="card-heading"><h3><ScanFace size={18}/> Face & liveness</h3><span className="badge neutral">Experimental</span></div><div className="metrics"><div><span>Face comparison</span><strong>{label(analysis?.face?.data.decision || event.payload.face_decision)}</strong></div><div><span>Cosine similarity</span><strong>{(analysis?.face?.data.cosine_similarity ?? event.payload.face_similarity)?.toFixed(4) ?? 'Unavailable'}</strong></div><div><span>Liveness</span><strong>Not verified</strong></div></div><p className="muted small">A face match does not certify identity, liveness or document authenticity.</p></section>
      <section className="card"><h3>Why this score?</h3><div className="contributions">{risk.contributions.map(c=><div className="contribution" key={c.name}><div><b>{label(c.name)}</b><p>{c.explanation}</p>{!c.complete&&<span className="small amber">Incomplete evidence</span>}</div><strong>+{c.points.toFixed(2)}<small>/ {c.weight}</small></strong></div>)}</div><details><summary>Policy provenance</summary><p className="small">{risk.policy_version}</p><code>{risk.policy_sha256}</code></details></section>
    </div><aside className="review-side"><RiskCard risk={risk}/><section className="card decision-card"><div className="card-heading"><h3><ShieldAlert size={18}/> Officer decision</h3></div><p className="muted small">Record your review independently of the model. Actor labels are unverified in this local demo.</p>
      {latest && <div className="decision-recorded"><Check size={16}/><div><b>{label(latest.payload.decision)} recorded</b><p>{latest.actor} · {new Date(latest.timestamp).toLocaleString()}</p><p>{latest.payload.note}</p></div></div>}
      <div className="decision-choices">{(['approve','secondary_inspection','reject'] as Decision[]).map(d=><button key={d} disabled={locked} aria-pressed={choice===d} className={choice===d?'selected':''} onClick={()=>{setChoice(d);setRequestId(crypto.randomUUID());}}>{label(d)}<ChevronRight size={15}/></button>)}</div>
      <label className="field">Review note<textarea placeholder="Explain the evidence behind your decision…" value={note} disabled={locked} onChange={e=>{setNote(e.target.value);setRequestId(crypto.randomUUID());}} maxLength={500}/><span className="small muted">8–500 characters. Do not include personal identifiers.</span></label>
      {choice==='approve'&&incomplete&&<label className="checkbox"><input type="checkbox" disabled={locked} checked={ack} onChange={e=>{setAck(e.target.checked);setRequestId(crypto.randomUUID());}}/>I reviewed the missing evidence and acknowledge this is an incomplete assessment.</label>}
      {error&&<div role="alert" className="error">{error}</div>}
      <button className="button primary full" disabled={!choice||note.trim().length<8||saving||(choice==='approve'&&incomplete&&!ack)} onClick={decide}>{saving?'Recording…':locked?'Retry same decision':'Record decision'}</button>
      <p className="small muted">Every decision is appended. Earlier decisions remain in the audit trail.</p>
    </section><section className="mini-note"><FileCheck2 size={20}/><div><b>Review metadata recorded</b><p>No document images, names or document numbers are retained.</p><code>{event.document_hash.slice(0,20)}…</code></div></section></aside></div>
  </div>;
}
