import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import Report, {RiskCard} from './Report';
import type { AuditEvent, Risk } from './types';

const risk:Risk={score:3.25,category:null,score_range:[3.25,24.25],evidence_coverage:.79,
  missing_required_signals:['liveness'],missing_signals:['liveness','metadata'],reasons:[],
  policy_version:'test-v1',policy_sha256:'a'.repeat(64),contributions:[]};
const event:AuditEvent={seq:1,event_id:'event',scan_id:'scan',timestamp:'2026-10-03T10:00:00Z',actor:'DEMO-01',document_hash:'a'.repeat(64),event_hash:'b'.repeat(64),kind:'scan',payload:{processing_status:'insufficient_evidence',document_type:'passport',risk,face_similarity:.9,face_decision:'match',duration_ms:100,layer_statuses:{},mismatch_fields:[]}};
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
describe('review evidence',()=>{
  it('never calls incomplete evidence Low and shows its point range',()=>{
    render(<RiskCard risk={risk}/>);expect(screen.getByText('Incomplete evidence')).toBeInTheDocument();
    expect(screen.queryByText(/Low observed risk/)).not.toBeInTheDocument();
    expect(screen.getByText(/3.25–24.25/)).toBeInTheDocument();
  });
  it('renders absent score as unknown',()=>{
    render(<RiskCard risk={{...risk,score:null,evidence_coverage:0}}/>);
    expect(screen.getByText('—')).toBeInTheDocument();
  });
  it('requires a note and explicit incomplete-evidence acknowledgement for approval',async()=>{
    const fetchMock=vi.fn().mockResolvedValue({ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>({...event,kind:'decision',event_hash:'c'.repeat(64),payload:{decision:'approve',note:'Synthetic review completed.',acknowledge_incomplete:true}})});
    vi.stubGlobal('fetch',fetchMock);
    render(<Report analysis={null} event={event} actor="DEMO-01" onRecorded={()=>{}}/>);
    fireEvent.click(screen.getByRole('button',{name:'Approve'}));
    fireEvent.change(screen.getByPlaceholderText(/Explain the evidence/),{target:{value:'Synthetic review completed.'}});
    expect(screen.getByRole('button',{name:'Record decision'})).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button',{name:'Record decision'}));
    await waitFor(()=>expect(fetchMock).toHaveBeenCalledOnce());
    const body=JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.expected_event_hash).toBe(event.event_hash);expect(body.acknowledge_incomplete).toBe(true);
    expect(await screen.findByText('Approve recorded')).toBeInTheDocument();
  });
  it('history explicitly excludes retained images and identity fields',()=>{
    render(<Report analysis={null} event={event} actor="DEMO-01" onRecorded={()=>{}}/>);
    expect(screen.getByText('Images were not retained')).toBeInTheDocument();
    expect(screen.getByRole('button',{name:'Record decision'})).toBeDisabled();
  });
  it('retries an uncertain decision with the same idempotency key',async()=>{
    const fetchMock=vi.fn().mockRejectedValue(new Error('Connection lost'));vi.stubGlobal('fetch',fetchMock);
    render(<Report analysis={null} event={event} actor="DEMO-01" onRecorded={()=>{}}/>);
    fireEvent.click(screen.getByRole('button',{name:'Secondary inspection'}));
    fireEvent.change(screen.getByPlaceholderText(/Explain the evidence/),{target:{value:'Synthetic review completed.'}});
    fireEvent.click(screen.getByRole('button',{name:'Record decision'}));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button',{name:'Retry same decision'}));
    await waitFor(()=>expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[0][1].body).toBe(fetchMock.mock.calls[1][1].body);
  });
});
