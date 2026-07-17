/**
 * Pure-TypeScript AKT inference (no Python/torch at runtime).
 *
 * Re-implements the compact AKT forward pass (kt/akt.py): KC+response
 * embeddings, causal right-shift, N post-norm TransformerEncoder layers
 * (MHA + ReLU FFN, PyTorch defaults), and a sigmoid head over
 * concat(hidden, kc_emb). Weights come from `kt.export_weights` JSON.
 *
 * Parity with torch is asserted by test fixtures generated from the same
 * checkpoint (tolerance 1e-4); dropout is inference-off, so eval outputs
 * are deterministic.
 */
import * as fs from "node:fs";

export interface AktWeights {
	hparams: { n_kc: number; d_model: number; n_heads: number; n_layers: number };
	state: Record<string, number[] | number[][]>;
}

type Vec = Float64Array;

function rows(m: number[][]): Vec[] {
	return m.map(r => Float64Array.from(r));
}

/** y = W x + b for row-major W (out x in). */
function matvec(w: Vec[], x: Vec, b?: Vec): Vec {
	const out = new Float64Array(w.length);
	for (let i = 0; i < w.length; i++) {
		const wi = w[i];
		let acc = b ? b[i] : 0;
		for (let j = 0; j < wi.length; j++) acc += wi[j] * x[j];
		out[i] = acc;
	}
	return out;
}

function layerNorm(x: Vec, gamma: Vec, beta: Vec, eps = 1e-5): Vec {
	let mean = 0;
	for (const v of x) mean += v;
	mean /= x.length;
	let variance = 0;
	for (const v of x) variance += (v - mean) ** 2;
	variance /= x.length;
	const denom = Math.sqrt(variance + eps);
	const out = new Float64Array(x.length);
	for (let i = 0; i < x.length; i++) out[i] = ((x[i] - mean) / denom) * gamma[i] + beta[i];
	return out;
}

function softmaxInPlace(x: Vec): void {
	let max = -Infinity;
	for (const v of x) if (v > max) max = v;
	let sum = 0;
	for (let i = 0; i < x.length; i++) {
		x[i] = Math.exp(x[i] - max);
		sum += x[i];
	}
	for (let i = 0; i < x.length; i++) x[i] /= sum;
}

interface Layer {
	inProjW: Vec[];
	inProjB: Vec;
	outProjW: Vec[];
	outProjB: Vec;
	linear1W: Vec[];
	linear1B: Vec;
	linear2W: Vec[];
	linear2B: Vec;
	norm1W: Vec;
	norm1B: Vec;
	norm2W: Vec;
	norm2B: Vec;
}

export class AktInference {
	readonly nKc: number;
	readonly dModel: number;
	readonly nHeads: number;
	private kcEmb: Vec[];
	private respEmb: Vec[];
	private layers: Layer[];
	private headW: Vec[];
	private headB: Vec;

	constructor(weights: AktWeights) {
		const { state, hparams } = weights;
		this.nKc = hparams.n_kc;
		this.dModel = hparams.d_model;
		this.nHeads = hparams.n_heads;
		const m2 = (key: string) => rows(state[key] as number[][]);
		const v1 = (key: string) => Float64Array.from(state[key] as number[]);
		this.kcEmb = m2("kc_emb.weight");
		this.respEmb = m2("resp_emb.weight");
		this.headW = m2("head.weight");
		this.headB = v1("head.bias");
		this.layers = [];
		for (let i = 0; i < hparams.n_layers; i++) {
			const p = `encoder.layers.${i}.`;
			this.layers.push({
				inProjW: m2(`${p}self_attn.in_proj_weight`),
				inProjB: v1(`${p}self_attn.in_proj_bias`),
				outProjW: m2(`${p}self_attn.out_proj.weight`),
				outProjB: v1(`${p}self_attn.out_proj.bias`),
				linear1W: m2(`${p}linear1.weight`),
				linear1B: v1(`${p}linear1.bias`),
				linear2W: m2(`${p}linear2.weight`),
				linear2B: v1(`${p}linear2.bias`),
				norm1W: v1(`${p}norm1.weight`),
				norm1B: v1(`${p}norm1.bias`),
				norm2W: v1(`${p}norm2.weight`),
				norm2B: v1(`${p}norm2.bias`),
			});
		}
	}

	static load(jsonPath: string): AktInference {
		return new AktInference(JSON.parse(fs.readFileSync(jsonPath, "utf-8")));
	}

	/** Mean KC embedding for a step (single id or multi-KC list; PAD=0 skipped). */
	private kcVec(kcs: number[]): Vec {
		const out = new Float64Array(this.dModel);
		let count = 0;
		for (const kc of kcs) {
			if (kc === 0) continue;
			const e = this.kcEmb[kc];
			for (let j = 0; j < this.dModel; j++) out[j] += e[j];
			count += 1;
		}
		if (count > 1) for (let j = 0; j < this.dModel; j++) out[j] /= count;
		return out;
	}

	/** Causal multi-head self-attention over the sequence (post-norm layer input). */
	private attention(layer: Layer, xs: Vec[]): Vec[] {
		const L = xs.length;
		const d = this.dModel;
		const headDim = d / this.nHeads;
		const scale = 1 / Math.sqrt(headDim);
		const qkv = xs.map(x => matvec(layer.inProjW, x, layer.inProjB)); // (L, 3d)
		const out: Vec[] = [];
		for (let t = 0; t < L; t++) {
			const merged = new Float64Array(d);
			for (let h = 0; h < this.nHeads; h++) {
				const qOff = h * headDim;
				const scores = new Float64Array(t + 1);
				for (let sPos = 0; sPos <= t; sPos++) {
					let dot = 0;
					for (let j = 0; j < headDim; j++) {
						dot += qkv[t][qOff + j] * qkv[sPos][d + qOff + j];
					}
					scores[sPos] = dot * scale;
				}
				softmaxInPlace(scores);
				for (let sPos = 0; sPos <= t; sPos++) {
					const w = scores[sPos];
					for (let j = 0; j < headDim; j++) {
						merged[qOff + j] += w * qkv[sPos][2 * d + qOff + j];
					}
				}
			}
			out.push(matvec(layer.outProjW, merged, layer.outProjB));
		}
		return out;
	}

	private encoderLayer(layer: Layer, xs: Vec[]): Vec[] {
		const attn = this.attention(layer, xs);
		const afterAttn = xs.map((x, t) => {
			const sum = new Float64Array(this.dModel);
			for (let j = 0; j < this.dModel; j++) sum[j] = x[j] + attn[t][j];
			return layerNorm(sum, layer.norm1W, layer.norm1B);
		});
		return afterAttn.map(x => {
			const hidden = matvec(layer.linear1W, x, layer.linear1B);
			for (let j = 0; j < hidden.length; j++) hidden[j] = Math.max(0, hidden[j]);
			const ffn = matvec(layer.linear2W, hidden, layer.linear2B);
			const sum = new Float64Array(this.dModel);
			for (let j = 0; j < this.dModel; j++) sum[j] = x[j] + ffn[j];
			return layerNorm(sum, layer.norm2W, layer.norm2B);
		});
	}

	/**
	 * P(correct) per step for one sequence. Each step is (kcs, resp); the
	 * last step's response is unused thanks to the causal shift, matching
	 * kt.train.mastery's convention.
	 */
	predict(steps: Array<{ kcs: number[]; resp: number }>): number[] {
		const L = steps.length;
		if (L === 0) return [];
		const kcVecs = steps.map(sStep => this.kcVec(sStep.kcs));
		const inter = steps.map((sStep, t) => {
			const e = this.respEmb[Math.min(Math.max(sStep.resp, 0), 1)];
			const out = new Float64Array(this.dModel);
			for (let j = 0; j < this.dModel; j++) out[j] = kcVecs[t][j] + e[j];
			return out;
		});
		// causal right-shift: position 0 sees zeros
		let hs: Vec[] = [new Float64Array(this.dModel), ...inter.slice(0, L - 1)];
		for (const layer of this.layers) hs = this.encoderLayer(layer, hs);
		return hs.map((h, t) => {
			const cat = new Float64Array(2 * this.dModel);
			cat.set(h);
			cat.set(kcVecs[t], this.dModel);
			const logit = matvec(this.headW, cat, this.headB)[0];
			return 1 / (1 + Math.exp(-logit));
		});
	}

	/** Mastery: P(correct) if the learner attempted kcId now (kt.train.mastery parity). */
	mastery(history: Array<[number, number]>, kcId: number): number {
		if (kcId > this.nKc) throw new Error(`kc_id ${kcId} outside model vocabulary (n_kc=${this.nKc})`);
		const steps = history.filter(([kc]) => kc <= this.nKc).map(([kc, resp]) => ({ kcs: [kc], resp }));
		steps.push({ kcs: [kcId], resp: 0 });
		const preds = this.predict(steps);
		return preds[preds.length - 1];
	}
}
