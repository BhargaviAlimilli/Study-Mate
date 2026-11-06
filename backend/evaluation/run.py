"""Fixed synthetic retrieval evaluation. Run from backend: python -m evaluation.run."""
import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from app.core.config import get_settings
from pathlib import Path
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from app.ai.embeddings import get_embedding_model


def run(with_model=False, threshold=0.45):
    fixture = json.loads(Path(__file__).with_name('cases.json').read_text())
    docs = [Document(page_content=p['text'],metadata={'document':p['document'],'page':p['page']}) for p in fixture['corpus']]
    store = QdrantVectorStore.from_documents(docs,embedding=get_embedding_model(),location=':memory:',collection_name='evaluation')
    rows=[]
    try:
        for case in fixture['questions']:
            started=time.perf_counter()
            matches=store.similarity_search_with_score(case['question'],k=4)
            ranks=[i for i,(doc,score) in enumerate(matches,1) if doc.metadata['document']==case['expected_document'] and doc.metadata['page']==case['expected_page']]
            selected=[doc for doc,score in matches if score>=threshold]
            row={**case,'retrieval_ms':round((time.perf_counter()-started)*1000,2),
                 'hit_at_4':bool(ranks),'reciprocal_rank':1/min(ranks) if ranks else 0,
                 'rejected_by_threshold':not selected,'top_score':float(matches[0][1]) if matches else None}
            if with_model:
                from app.ai.llm import generate_reply
                result=asyncio.run(asyncio.wait_for(generate_reply(case['question'],[{'citation_id':i,'text':doc.page_content} for i,(doc,score) in enumerate(matches,1)]),timeout=60))
                row.update(model_status=result.status, status_matches=result.status==case['expected_status'],
                           valid_citation_ids=all(1<=i<=len(matches) for i in result.citation_ids), answer=result.answer)
            rows.append(row)
    finally:
        store.client.close()
    supported=[r for r in rows if r['expected_document']]
    unsupported=[r for r in rows if not r['expected_document']]
    return {'generated_at':datetime.now(timezone.utc).isoformat(),'embedding_model':get_settings().embedding_model_name,'chat_model':get_settings().anthropic_model if with_model else None,'dataset_size':len(rows),'supported_questions':len(supported),'unsupported_questions':len(unsupported),
        'recall_at_4':sum(r['hit_at_4'] for r in supported)/len(supported),
        'mean_reciprocal_rank':sum(r['reciprocal_rank'] for r in supported)/len(supported),
        'unsupported_threshold_rejection_rate':sum(r['rejected_by_threshold'] for r in unsupported)/len(unsupported),
        'mean_retrieval_ms':sum(r['retrieval_ms'] for r in rows)/len(rows), 'score_threshold':threshold,
        'limitations':'Synthetic text passages, not a production PDF benchmark. Citation IDs do not prove answer support. Human review is required for groundedness and quiz correctness. The threshold rejection metric is diagnostic only. Model evaluation receives all top-four passages, as production chat does. Human review is needed to assess whether citations actually support answers.',
        'results':rows}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--with-model',action='store_true')
    parser.add_argument('--threshold',type=float,default=0.45)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    report=run(args.with_model,args.threshold)
    payload=json.dumps(report,indent=2)
    if args.output:
        args.output.write_text(payload,encoding='utf-8')
    print(payload)
