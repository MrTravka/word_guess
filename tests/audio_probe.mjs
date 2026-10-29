export const audioProbe = `(() => {
  const Native = window.AudioContext;
  window.audioContexts=[]; window.effectCount=0; window.mediaSourceCount=0;
  window.AudioContext=class extends Native {
    constructor(...args){super(...args); window.audioContexts.push(this)}
    createOscillator(){window.effectCount++; return super.createOscillator()}
    createMediaElementSource(media){
      window.mediaSourceCount++;
      const node=super.createMediaElementSource(media), connect=node.connect.bind(node);
      node.connect=(destination)=>{window.musicGain=destination; return connect(destination)};
      return node;
    }
  };
})()`

export const analyseAudio = `(async () => {
  const bytes=await fetch('/audio/ost.mp3').then(r=>r.arrayBuffer());
  const buffer=await new OfflineAudioContext(2,1,44100).decodeAudioData(bytes);
  const channels=Array.from({length:buffer.numberOfChannels},(_,i)=>buffer.getChannelData(i));
  const rms=(start,end)=>{
    let sum=0,n=0;
    for(const data of channels) for(let i=start;i<end;i++){sum+=data[i]*data[i];n++}
    return Math.sqrt(sum/n);
  };
  let peak=0;
  for(const data of channels) for(const value of data) peak=Math.max(peak,Math.abs(value));
  const report={duration:buffer.duration,sample_rate:buffer.sampleRate,channels:channels.length,
    peak,rms:rms(0,buffer.length),start_100ms_rms:rms(0,4410),end_100ms_rms:rms(buffer.length-4410,buffer.length),
    boundary_difference:Math.max(...channels.map(data=>Math.abs(data.at(-1)-data[0]))),
    method:'Chrome OfflineAudioContext decode; original file unchanged; listening not performed'};
  // A short review file: last two seconds followed by the first two, never used in production.
  const frames=buffer.sampleRate*4, view=new DataView(new ArrayBuffer(44+frames*channels.length*2));
  const word=(offset,text)=>{for(let i=0;i<text.length;i++)view.setUint8(offset+i,text.charCodeAt(i))};
  word(0,'RIFF');view.setUint32(4,view.byteLength-8,true);word(8,'WAVE');word(12,'fmt ');
  view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,channels.length,true);
  view.setUint32(24,buffer.sampleRate,true);view.setUint32(28,buffer.sampleRate*channels.length*2,true);
  view.setUint16(32,channels.length*2,true);view.setUint16(34,16,true);word(36,'data');view.setUint32(40,view.byteLength-44,true);
  for(let frame=0;frame<frames;frame++)for(let channel=0;channel<channels.length;channel++){
    const source=frame<frames/2?buffer.length-frames/2+frame:frame-frames/2;
    const sample=Math.max(-1,Math.min(1,channels[channel][source]));
    view.setInt16(44+(frame*channels.length+channel)*2,Math.round(sample*32767),true);
  }
  let binary='';for(const byte of new Uint8Array(view.buffer))binary+=String.fromCharCode(byte);
  return {report,seam_wav:btoa(binary)};
})()`
