import type {SimulationState} from './types';
const API=import.meta.env.VITE_API_URL??'';
export const exportUrl=(file='export')=>`${API}/api/${file}`;
export async function request(path:string,body?:unknown):Promise<SimulationState>{
 const r=await fetch(`${API}/api/${path}`,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));return data;
}
export function connectLive(accept:(s:SimulationState)=>void,status:(connected:boolean)=>void){
 let closed=false,socket:WebSocket|undefined,retry:number|undefined;
 function connect(){socket=new WebSocket(`${API?API.replace(/^http/,'ws'):`${location.protocol==='https:'?'wss':'ws'}://${location.host}`}/api/live`);socket.onopen=()=>status(true);socket.onmessage=e=>accept(JSON.parse(e.data));socket.onerror=()=>socket?.close();socket.onclose=()=>{status(false);if(!closed)retry=window.setTimeout(connect,1500);};}connect();
 return ()=>{closed=true;window.clearTimeout(retry);socket?.close();};
}
