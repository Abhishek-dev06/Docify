import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import App from './App';
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
const jsonResponse = (body:unknown) => ({ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>body});
it('disables scan submission until a document is selected',()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(jsonResponse({ocr_available:true,audit_persistent:true})));
  render(<App/>);expect(screen.getByRole('button',{name:'Analyze & record'})).toBeDisabled();
  expect(screen.getByLabelText('Document image')).toHaveAttribute('accept','image/jpeg,image/png,image/webp');
});
it('shows a truthful empty history rather than fabricated records',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(jsonResponse({items:[],total:0,offset:0})));
  render(<App/>);fireEvent.click(screen.getByRole('button',{name:'Review history'}));
  expect(await screen.findByText('No matching reviews')).toBeInTheDocument();
});
it('warns when a connected serverless backend lacks complete capabilities',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(jsonResponse({ocr_available:false,audit_persistent:false})));
  render(<App/>);
  expect(await screen.findByText(/OCR is unavailable and review history is temporary/)).toBeInTheDocument();
});
