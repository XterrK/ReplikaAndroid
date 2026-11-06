#!/usr/bin/env python3
"""Compare embedded ONNX initializer tensors with mmap and no ONNX/PyTorch dependency.

ONNX protobuf fields: ModelProto.graph=7; GraphProto.initializer=5;
TensorProto.name=8, raw_data=9. Non-raw typed tensor payloads are hashed too.
File-byte differences alone do not prove trained weights differ.
"""
import argparse,hashlib,json,mmap,pathlib

def varint(data,pos):
    value=0;shift=0
    while True:
        b=data[pos];pos+=1;value|=(b&127)<<shift
        if not b&128:return value,pos
        shift+=7
        if shift>70:raise ValueError('Invalid protobuf varint')

def fields(data,begin,end):
    pos=begin
    while pos<end:
        key,pos=varint(data,pos);number=key>>3;wire=key&7
        if wire==0:
            value,following=varint(data,pos);yield number,wire,pos,following,value;pos=following
        elif wire in (1,5):
            following=pos+(8 if wire==1 else 4);yield number,wire,pos,following,None;pos=following
        elif wire==2:
            n,pos=varint(data,pos);following=pos+n
            if following>end:raise ValueError('Truncated protobuf field')
            yield number,wire,pos,following,None;pos=following
        else:raise ValueError(f'Unsupported protobuf wire type{wire}')

def initializers(path):
    result={}
    with path.open('rb') as stream,mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ) as data:
        graph=next((a,b) for number,wire,a,b,_ in fields(data,0,len(data)) if number==7 and wire==2)
        for number,wire,a,b,_ in fields(data,*graph):
            if number!=5 or wire!=2:continue
            name=None;digest=hashlib.sha256();size=0;has_payload=False
            for field,w,start,end,value in fields(data,a,b):
                if field==8 and w==2:name=data[start:end].decode()
                if field in (1,2,4,5,6,7,9,10,11):
                    digest.update(bytes([field,w]));view=memoryview(data)[start:end];digest.update(view);view.release()
                    size+=end-start
                    if field in (4,5,6,7,9,10,11):has_payload=True
            if name is None or not has_payload:raise ValueError('Unnamed or external tensor; cannot prove equality')
            if name in result:raise ValueError('Duplicate tensor name')
            result[name]={'sha256':digest.hexdigest(),'bytesIncludingShapeType':size}
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--left',type=pathlib.Path,required=True);p.add_argument('--right',type=pathlib.Path,required=True);p.add_argument('--out',type=pathlib.Path,required=True);a=p.parse_args()
    x=initializers(a.left);y=initializers(a.right);common=set(x)&set(y);different=sorted(n for n in common if x[n]!=y[n]);left_only=sorted(set(x)-set(y));right_only=sorted(set(y)-set(x))
    out={'method':'Embedded ONNX initializer name/shape/type/payload hashes; metadata and graph operations are not compared','left':str(a.left),'right':str(a.right),'leftInitializers':len(x),'rightInitializers':len(y),'commonNames':len(common),'differentInitializers':len(different),'differentInitializerNames':different,'leftOnly':left_only,'rightOnly':right_only,'allEmbeddedInitializersEqual':not different and not left_only and not right_only,'leftTensors':x,'rightTensors':y}
    a.out.write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items() if k not in ['leftTensors','rightTensors','differentInitializerNames']},indent=2))

if __name__=='__main__':main()
