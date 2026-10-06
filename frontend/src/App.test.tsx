import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import App from './App';
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
it('disables scan submission until a document is selected',()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({})}));
  render(<App/>);expect(screen.getByRole('button',{name:'Analyze & record'})).toBeDisabled();
  expect(screen.getByLabelText('Document image')).toHaveAttribute('accept','image/jpeg,image/png,image/webp');
});
it('shows a truthful empty history rather than fabricated records',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({items:[],total:0,offset:0})}));
  render(<App/>);fireEvent.click(screen.getByRole('button',{name:'Review history'}));
  expect(await screen.findByText('No matching reviews')).toBeInTheDocument();
});
