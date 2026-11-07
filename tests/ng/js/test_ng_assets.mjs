import assert from "node:assert/strict";
import {assetChoices,assetSubjects,relationNames,referenceSubject,restoreAssetWidget,assetPanel} from "../../../js/ng/ng_asset_relations.js";
import {subjectChoices} from "../../../js/ng/ng_subjects.js";
const alice={media:"image",widgets:{context_id:"alice",name:"Alice",image:"same.png",content:"character",usage:"reference"}};
const coat={media:"image",widgets:{context_id:"coat",name:"Coat",image:"same.png",content:"outfit",usage:"reference",subject_ids:'["alice"]'}};
const frame={media:"image",widgets:{context_id:"frame",name:"Start",image:"same.png",content:"character",usage:"first_frame"}};
assert.equal(referenceSubject(alice),true);assert.equal(referenceSubject(coat),false);assert.equal(referenceSubject(frame),false);
assert.deepEqual(assetChoices([alice,coat,frame],[],"coat"),[{id:"alice",name:"Alice"}]);
assert.deepEqual(assetChoices([alice],["missing"],"alice"),[{id:"missing",name:"missing (not connected or not a Subject)"}]);
assert.deepEqual(subjectChoices([alice,coat,frame]),[{id:"alice",name:"Alice"}],"a linked asset and first frame cannot become voice targets");
assert.equal(relationNames(coat,[{...alice,widgets:{...alice.widgets,name:"Renamed"}},coat]),"Renamed");
for(const value of ["bad","{}",'[1]',undefined])assert.deepEqual(assetSubjects({widgets:{subject_ids:value}}),[]);
for(const value of ["image","video",undefined]){const widget={name:"subject_ids",value};restoreAssetWidget({widgets:[widget]});assert.equal(widget.value,"");}
const widget={name:"subject_ids",value:'["alice"]'};restoreAssetWidget({widgets:[widget]});assert.equal(widget.value,'["alice"]');
assert.equal(assetPanel({widgets:[]}),null,"never offer a setting the running Python schema cannot consume");
console.log("ng assets: ownership, choices, stable IDs, missing targets and old schema checks passed");
