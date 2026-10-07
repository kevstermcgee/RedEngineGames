'use strict';
self.onmessage=async()=>{try{
 const t=performance.now(),res=await fetch('music.wav');if(!res.ok)throw Error('Music could not load');
 const b=await res.arrayBuffer(),v=new DataView(b);let rate=44100,channels=2,bits=16,offset=0,size=0;
 for(let at=12;at+8<=b.byteLength;){const tag=String.fromCharCode(...new Uint8Array(b,at,4)),n=v.getUint32(at+4,true);if(tag==='fmt '){if(v.getUint16(at+8,true)!==1)throw Error('Expected PCM');channels=v.getUint16(at+10,true);rate=v.getUint32(at+12,true);bits=v.getUint16(at+22,true);}if(tag==='data'){offset=at+8;size=n;break;}at+=8+n+(n%2);}
 if(!offset||channels!==2||bits!==16)throw Error('Unsupported music WAV');
 const pcm=new Float32Array(size/2);for(let i=0;i<pcm.length;i++)pcm[i]=v.getInt16(offset+i*2,true)/32768;
 self.postMessage({ok:true,pcm,rate,ms:Math.round(performance.now()-t)},[pcm.buffer]);
}catch(e){self.postMessage({ok:false,error:String(e.message||e)});}};
