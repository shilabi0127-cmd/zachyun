import copy
import pytest
from localresearch.pipeline import ContextPolicy, select_context, run, replay, save_record


def hit(id, path="one.md", size=64):
    return {"id":id,"path":path,"heading":"note","start_line":1,"end_line":2,
            "text":"local evidence "*(size//15)+"x"*(size%15)}


def test_context_budget_and_document_diversity():
    candidates=[hit("a"),hit("a"),hit("b"),hit("c"),hit("d","two.md"),hit("e","three.md")]
    selected,info=select_context(candidates,4,ContextPolicy(max_chars=200))
    assert [h["id"] for h in selected]==["a","b","d"]
    assert info["context_chars"]<=200
    assert info["skipped"]["duplicate"]==1
    assert info["skipped"]["document_limit"]==1
    assert info["skipped"]["budget"]==1


def test_oversized_chunk_is_not_silently_truncated():
    selected,info=select_context([hit("long",size=700),hit("short",size=64)],2,ContextPolicy(max_chars=128))
    assert selected[0]["id"]=="short" and info["skipped"]["budget"]==1


class StubIndex:
    def search(self,question,k=4):return [hit("a")]


def test_replay_is_independent_of_current_documents(tmp_path):
    record=run(StubIndex(),"local evidence")
    path=tmp_path/"run.json";save_record(record,path)
    result=replay(record)
    assert result["items"]==record["items"]
    assert result["replay_of"]==record["trace"]["input_sha256"]
    assert record["trace"]["timing_ms"]["total"]>=0


def test_changed_saved_source_fails_integrity_check():
    record=run(StubIndex(),"local evidence")
    record["trace"]["inputs"]["hits"][0]["text"]="changed"
    with pytest.raises(ValueError,match="hash mismatch"):replay(record)


def test_replay_requires_matching_prompt_version():
    record=run(StubIndex(),"local evidence")
    record["trace"]["version"]=99
    with pytest.raises(ValueError,match="version"):replay(record)


@pytest.mark.parametrize("question,k,backend",[(" ",4,"extractive"),("q",0,"extractive"),("q",4,"remote"),("q",True,"extractive")])
def test_bad_requests_fail_before_retrieval(question,k,backend):
    with pytest.raises(ValueError):run(StubIndex(),question,k,backend)


def test_empty_retrieval_is_explicit():
    class Empty:
        def search(self,question,k=4):return []
    result=run(Empty(),"unknown")
    assert result["refused"] and result["trace"]["context_chars"]==0
