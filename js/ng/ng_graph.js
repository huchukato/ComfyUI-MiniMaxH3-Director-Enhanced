// Follow this project's downstream graph so its Director displays its sampler's events.
export function downstreamNodes(node) {
  const graph=node.graph, found=[], visited=new Set([String(node.id)]), pending=[node];
  while(pending.length) {
    const current=pending.shift();
    for(const output of current.outputs||[]) for(const id of output.links||[]) {
      const link=graph?.links?.[id]??graph?.getLink?.(id), target=link&&graph.getNodeById(link.target_id);
      if(!target||visited.has(String(target.id)))continue;
      visited.add(String(target.id));found.push(target);pending.push(target);
    }
  }
  return found;
}

export function projectRenderIds(node) {
  return [node.id,...downstreamNodes(node).map((entry)=>entry.id)];
}

export function hasRenderPath(node) {
  return downstreamNodes(node).some((entry)=>["NGProjectRender","SamplerCustomAdvanced","KSampler","KSamplerAdvanced"].includes(entry.comfyClass));
}
