#!/usr/bin/env node
import * as bril from './bril';
import {readStdin, callPython, unreachable} from './util';
import {ChildProcess, ExecException} from "child_process";
import {Instruction, Label} from "./bril";

/**
 * An interpreter error to print to the console.
 */
class BriliError extends Error {
  constructor(message?: string) {
    super(message);
    Object.setPrototypeOf(this, new.target.prototype);
    this.name = BriliError.name;
  }
}

/**
 * Create an interpreter error object to throw.
 */
function error(message: string): BriliError {
  return new BriliError(message);
}

function debugMessage(message: string): void {
  console.error(message);
}

/**
 * An abstract key class used to access the heap.
 * This allows for "pointer arithmetic" on keys,
 * while still allowing lookups based on the based pointer of each allocation.
 */
export class Key {
    readonly base: number;
    readonly offset: number;

    constructor(b: number, o: number) {
        this.base = b;
        this.offset = o;
    }

    add(offset: number) {
        return new Key(this.base, this.offset + offset);
    }
}

/**
 * A Heap maps Keys to arrays of a given type.
 */
export class Heap<X> {

    private readonly storage: Map<number, X[]>
    constructor() {
        this.storage = new Map()
    }

    isEmpty(): boolean {
        return this.storage.size == 0;
    }

    private count = 0;
    private getNewBase():number {
        let val = this.count;
        this.count++;
        return val;
    }

    private freeKey(key:Key) {
        return;
    }

    alloc(amt:number): Key {
        if (amt <= 0) {
            throw error(`cannot allocate ${amt} entries`);
        }
        let base = this.getNewBase();
        this.storage.set(base, new Array(amt))
        return new Key(base, 0);
    }

    free(key: Key) {
        if (this.storage.has(key.base) && key.offset == 0) {
            this.freeKey(key);
            this.storage.delete(key.base);
        } else {
            throw error(`Tried to free illegal memory location base: ${key.base}, offset: ${key.offset}. Offset must be 0.`);
        }
    }

    write(key: Key, val: X) {
        let data = this.storage.get(key.base);
        if (data && data.length > key.offset && key.offset >= 0) {
            data[key.offset] = val;
        } else {
            throw error(`Uninitialized heap location ${key.base} and/or illegal offset ${key.offset}`);
        }
    }

    read(key: Key): X {
        let data = this.storage.get(key.base);
        if (data && data.length > key.offset && key.offset >= 0) {
            return data[key.offset];
        } else {
            throw error(`Uninitialized heap location ${key.base} and/or illegal offset ${key.offset}`);
        }
    }

    log_heap() {
        debugMessage("Heap");
        this.storage.forEach( (value: X[], key: number) => {
            debugMessage(`${key}: ${value}`);
        });
    }
}

export class RefCounter {
  private readonly refcounts: Map<number, number>;
  private readonly deadrefs: Set<number>;
  private readonly heap: Heap<Value>;

  constructor(heap: Heap<Value>) {
    this.refcounts = new Map();
    this.deadrefs = new Set();
    this.heap = heap;
  }

  count(key: Key): number {
    let count = this.refcounts.get(key.base);;
    let dead_count = this.deadrefs.has(key.base) ? 1 : 0
    count = count ? count : 0;
    return count + dead_count
  }

  increment(key: Key) {
    this.refcounts.set(key.base, this.count(key) + 1);
    //debugMessage(`Incrementing ${key.base} to ${this.count(key)}`);
  }

  decrement(key: Key, deletion_handled: boolean=false, reason: string="") {
    this.refcounts.set(key.base, this.count(key) - 1);

    if (deletion_handled) {
      if (this.deadrefs.has(key.base)) {
        throw error(`maybe double freed pointer with base ${key.base}`);
      }
      this.deadrefs.add(key.base);
    }

    //debugMessage(`Decrementing ${key.base} to ${this.count(key)} for ${reason}`);

    if (!deletion_handled){ this.free_if_norefs(key); }
  }

  free_if_norefs(key: Key) {
    if (this.count(key) == 0) {
      // need to free w/ offset 0
      let key_base = new Key(key.base, 0);
      this.heap.free(key_base);
      this.refcounts.delete(key.base);
    }
  }

  cleanup_environment(env: Env, ret: Value | null) {
    env.forEach((value: Value, key: bril.Ident) => {
      if (isPointer(value) && value != ret) {
        let key = (<Pointer> value).loc
        if (this.deadrefs.has(key.base)) {
          this.deadrefs.delete(key.base);
          this.free_if_norefs(key);
        } else {
          this.decrement(key, false, "cleanup");
        }
      }
    });
  }

  has_deadref(key: Key): boolean {
    return this.deadrefs.has(key.base)
  }
}

const argCounts: {[key in bril.OpCode]: number | null} = {
  add: 2,
  mul: 2,
  sub: 2,
  div: 2,
  id: 1,
  lt: 2,
  le: 2,
  gt: 2,
  ge: 2,
  eq: 2,
  not: 1,
  and: 2,
  or: 2,
  fadd: 2,
  fmul: 2,
  fsub: 2,
  fdiv: 2,
  flt: 2,
  fle: 2,
  fgt: 2,
  fge: 2,
  feq: 2,
  print: null,  // Any number of arguments.
  br: 1,
  jmp: 0,
  ret: null,  // (Should be 0 or 1.)
  nop: 0,
  call: null,
  alloc: 1,
  free: 1,
  store: 2,
  load: 1,
  ptradd: 2,
  phi: null,
  speculate: 0,
  guard: 1,
  commit: 0,
};

type Pointer = {
  loc: Key;
  type: bril.Type;
}

type Value = boolean | BigInt | Pointer | number;
type Env = Map<bril.Ident, Value>;

/**
 * Check whether a run-time value matches the given static type.
 */
function typeCheck(val: Value, typ: bril.Type): boolean {
  if (typ === "int") {
    return typeof val === "bigint";
  } else if (typ === "bool") {
    return typeof val === "boolean";
  } else if (typ === "float") {
    return typeof val === "number";
  } else if (typeof typ === "object" && typ.hasOwnProperty("ptr")) {
    return val.hasOwnProperty("loc");
  }
  throw error(`unknown type ${typ}`);
}


function isPointer(val: Value): boolean {
  return val.hasOwnProperty("loc");
}

/**
 * Check whether the types are equal.
 */
function typeCmp(lhs: bril.Type, rhs: bril.Type): boolean {
  if (lhs === "int" || lhs == "bool" || lhs == "float") {
    return lhs == rhs;
  } else {
    if (typeof rhs === "object" && rhs.hasOwnProperty("ptr")) {
      return typeCmp(lhs.ptr, rhs.ptr);
    } else {
      return false;
    }
  }
}

function get(env: Env, ident: bril.Ident) {
  let val = env.get(ident);
  if (typeof val === 'undefined') {
    throw error(`undefined variable ${ident}`);
  }
  return val;
}

function findFunc(func: bril.Ident, funcs: readonly bril.Function[]) {
  let matches = funcs.filter(function (f: bril.Function) {
    return f.name === func;
  });

  if (matches.length == 0) {
    throw error(`no function of name ${func} found`);
  } else if (matches.length > 1) {
    throw error(`multiple functions of name ${func} found`);
  }

  return matches[0];
}

function alloc(ptrType: bril.ParamType, amt:number, heap:Heap<Value>): Pointer {
  if (typeof ptrType != 'object') {
    throw error(`unspecified pointer type ${ptrType}`);
  } else if (amt <= 0) {
    throw error(`must allocate a positive amount of memory: ${amt} <= 0`);
  } else {
    let loc = heap.alloc(amt)
    let dataType = ptrType.ptr;
    return {
      loc: loc,
      type: dataType
    }
  }
}

/**
 * Ensure that the instruction has exactly `count` arguments,
 * throw an exception otherwise.
 */
function checkArgs(instr: bril.Operation, count: number) {
  let found = instr.args ? instr.args.length : 0;
  if (found != count) {
    throw error(`${instr.op} takes ${count} argument(s); got ${found}`);
  }
}

function getPtr(instr: bril.Operation, env: Env, index: number): Pointer {
  let val = getArgument(instr, env, index);
  if (typeof val !== 'object' || val instanceof BigInt) {
    throw `${instr.op} argument ${index} must be a Pointer`;
  }
  return val;
}

function getArgument(instr: bril.Operation, env: Env, index: number, typ?: bril.Type) {
  let args = instr.args || [];
  if (args.length <= index) {
    throw error(`${instr.op} expected at least ${index+1} arguments; got ${args.length}`);
  }
  let val = get(env, args[index]);
  if (typ && !typeCheck(val, typ)) {
    throw error(`${instr.op} argument ${index} must be a ${typ}`);
  }
  return val;
}

function getInt(instr: bril.Operation, env: Env, index: number): bigint {
  return getArgument(instr, env, index, 'int') as bigint;
}

function getBool(instr: bril.Operation, env: Env, index: number): boolean {
  return getArgument(instr, env, index, 'bool') as boolean;
}

function getFloat(instr: bril.Operation, env: Env, index: number): number {
  return getArgument(instr, env, index, 'float') as number;
}

function getLabel(instr: bril.Operation, index: number): bril.Ident {
  if (!instr.labels) {
    throw error(`missing labels; expected at least ${index+1}`);
  }
  if (instr.labels.length <= index) {
    throw error(`expecting ${index+1} labels; found ${instr.labels.length}`);
  }
  return instr.labels[index];
}

function getFunc(instr: bril.Operation, index: number): bril.Ident {
  if (!instr.funcs) {
    throw error(`missing functions; expected at least ${index+1}`);
  }
  if (instr.funcs.length <= index) {
    throw error(`expecting ${index+1} functions; found ${instr.funcs.length}`);
  }
  return instr.funcs[index];
}

/**
 * Name the basic block based on the current state
 * This mirrors compilers/cfg.func_prefix
 */
function blockName(state: State): string {
  let prefix = '';
  if (state.funcs.length > 1 && state.curfunc && state.curfunc.name) {
    prefix = `${state.curfunc.name}.`;
  }
  let label = state.curlabel || 'entry';
  return `${prefix}${label}`;
}

/**
 * Fix the dom to be Map<string, Set<string>>, not Map<string, string[]>
 */
function domToSet(dom: Map<string, string[]>) {
  let ans = new Map<string, Set<string>>();
  debugMessage(dom);
  for (const [key, setlist] of Object.entries(dom)) {
    let set = new Set<string>();
    setlist.forEach((value: string) => {
      set.add(value);
    })
    ans.set(key, set);
  }
  return ans;
}

/**
 * Reset the trace
 */
function resetTrace(state: State): void {
  // reset the tracing state
  state.tracing = false;
  state.trace_start = null;
  state.blocks = [];
  state.instrs = [];
}

function transcribeTrace(
    trace_start_label: string, trace_end_label: string, skip_postfix: string,
    trace: (Instruction | Label)[]
): (Instruction | Label)[] {
  let newinstrs = new Array<(Instruction | Label)>();
  let skip_label = `${trace_start_label}${skip_postfix}`;

  newinstrs.push({'op': 'speculate'});
  for (let i = 0; i < trace.length; ++i) {
    let instr = trace[i];
    if ('dest' in instr && instr.type == 'bool') {
      newinstrs.push(instr);
    } else if ('op' in instr && instr.op == 'jmp' || 'label' in instr) {
      // skip it
    } else if ('op' in instr && instr.op == 'br' && instr.args) {
      // replace breaks with guards
      if (i + 1 < trace.length) {
        let nextinstr = trace[i + 1];
        let cond = instr.args[0]
        // figure out where we went
        if ('label' in nextinstr) {
          if (nextinstr.label == getLabel(instr, 0)) {
            newinstrs.push({'op': 'guard', 'args': [cond], 'labels': [skip_label]})
          } else {
            let not_cond = `not_${cond}`;
            newinstrs.push(
                {'op': 'not', 'args': [cond], 'type': 'bool', 'dest': not_cond}
            )
            newinstrs.push(
                {'op': 'guard', 'args': [not_cond], 'labels': [skip_label]}
            )
          }
        } else {
          error(`Next instruction in trace dafter br ${instr} was not instr`);
        }
      }
    }
  }
  newinstrs.push({'op': 'commit'});
  newinstrs.push({'op': 'jmp', 'labels': [trace_end_label]});
  newinstrs.push({'label': skip_label});

  return newinstrs
}

/**
 * Finalize the trace
 */
function finalizeTrace(state: State): void {
  debugMessage(state.instrs);
  if (!state.curlabel) { error("State had no current label, malformed"); return;}
  if (!state.trace_start) { error("State had no trace start, malformed");}
  if (!state.curfunc) { error("State had no current function, malformed");}
  if (state.curlabel != state.trace_start) { error("Traced a non-loop, malformed");}

  let skip_postfix = `${state.curfunc.instrs.length}`;
  let newinstrs = new Array<(Instruction | Label)>();
  let straightlineinstrs = transcribeTrace(
      state.curlabel, state.curlabel, skip_postfix, state.instrs
  );
  let spliced = false;
  state.curfunc.instrs.forEach((instr) => {
    if (instr) {newinstrs.push(instr);}
    if (instr && 'label' in instr && instr.label == state.trace_start) {
      if (spliced) { error("Tried to splice twice");}
      straightlineinstrs.forEach((value) => {
        if (value) {newinstrs.push(value);}
      });
      spliced = true;
    }
  });

  debugMessage(`replacing ${JSON.stringify(state.curfunc.instrs)}`);
  debugMessage(`with ${JSON.stringify(newinstrs)}`);
  state.curfunc.instrs = newinstrs;
  resetTrace(state);
}

/**
 * The thing to do after interpreting an instruction: this is how `evalInstr`
 * communicates control-flow actions back to the top-level interpreter loop.
 */
type Action =
  {"action": "next"} |  // Normal execution: just proceed to next instruction.
  {"action": "jump", "label": bril.Ident} |
  {"action": "end", "ret": Value | null} |
  {"action": "speculate"} |
  {"action": "commit"} |
  {"action": "abort", "label": bril.Ident};
let NEXT: Action = {"action": "next"};

/**
 * The interpreter state that's threaded through recursive calls.
 */
type State = {
  env: Env,
  readonly heap: Heap<Value>,
  readonly refcounter: RefCounter,
  readonly funcs: readonly bril.Function[],

  // For profiling: a total count of the number of instructions executed.
  icount: bigint,

  // For SSA (phi-node) execution: keep track of recently-seen labels.
  curlabel: string | null,
  lastlabel: string | null,

  // For speculation: the state at the point where speculation began.
  specparent: State | null,

  // For tracing:
  tracing: boolean,
  readonly dom: Map<string, Set<string>>,
  backedge_dests: Set<string>,
  trace_start: string | null,
  curfunc: bril.Function, // current function
  blocks: string[], // blocks traversed
  instrs: (Instruction | Label)[],
}

/**
 * Interpet a call instruction.
 */
function evalCall(instr: bril.Operation, state: State): Action {
  // Which function are we calling?
  let funcName = getFunc(instr, 0);
  let func = findFunc(funcName, state.funcs);
  if (func === null) {
    throw error(`undefined function ${funcName}`);
  }

  let newEnv: Env = new Map();

  // Check arity of arguments and definition.
  let params = func.args || [];
  let args = instr.args || [];
  if (params.length !== args.length) {
    throw error(`function expected ${params.length} arguments, got ${args.length}`);
  }

  for (let i = 0; i < params.length; i++) {
    // Look up the variable in the current (calling) environment.
    let value = get(state.env, args[i]);

    // Check argument types
    if (!typeCheck(value, params[i].type)) {
      throw error(`function argument type mismatch`);
    }

    // Set the value of the arg in the new (function) environment.
    newEnv.set(params[i].name, value);
    if(isPointer(value)) {
      state.refcounter.increment((<Pointer> value).loc)
    }
  }

  // Invoke the interpreter on the function.
  let newState: State = {
    env: newEnv,
    heap: state.heap,
    funcs: state.funcs,
    icount: state.icount,
    refcounter: state.refcounter,
    lastlabel: null,
    curlabel: null,
    specparent: null,  // Speculation not allowed.

    tracing: false,
    dom: state.dom,
    backedge_dests: state.backedge_dests,
    trace_start: null,
    curfunc: func,
    blocks: [],
    instrs: [],
  }

  // Don't need to update func since we send over a new state
  let retVal = evalFunc(func, newState);
  state.icount = newState.icount;

  // Dynamically check the function's return value and type.
  if (!('dest' in instr)) {  // `instr` is an `EffectOperation`.
     // Expected void function
    if (retVal !== null) {
      throw error(`unexpected value returned without destination`);
    }
    if (func.type !== undefined) {
      throw error(`non-void function (type: ${func.type}) doesn't return anything`);
    }
  } else {  // `instr` is a `ValueOperation`.
    // Expected non-void function
    if (instr.type === undefined) {
      throw error(`function call must include a type if it has a destination`);
    }
    if (instr.dest === undefined) {
      throw error(`function call must include a destination if it has a type`);
    }
    if (retVal === null) {
      throw error(`non-void function (type: ${func.type}) doesn't return anything`);
    }
    if (!typeCheck(retVal, instr.type)) {
      throw error(`type of value returned by function does not match destination type`);
    }
    if (func.type === undefined) {
      throw error(`function with void return type used in value call`);
    }
    if (!typeCmp(instr.type, func.type)) {
      throw error(`type of value returned by function does not match declaration`);
    }
    state.env.set(instr.dest, retVal);
  }
  return NEXT;
}

/**
 * Interpret an instruction in a given environment, possibly updating the
 * environment. If the instruction branches to a new label, return that label;
 * otherwise, return "next" to indicate that we should proceed to the next
 * instruction or "end" to terminate the function.
 */
function evalInstr(instr: bril.Instruction, state: State): Action {
  state.icount += BigInt(1);

  // Check that we have the right number of arguments.
  if (instr.op !== "const") {
    let count = argCounts[instr.op];
    if (count === undefined) {
      throw error("unknown opcode " + instr.op);
    } else if (count !== null) {
      checkArgs(instr, count);
    }
  }

  // Function calls are not (currently) supported during speculation.
  // It would be cool to add, but aborting from inside a function call
  // would require explicit stack management.
  if (state.specparent && ['call', 'ret'].includes(instr.op)) {
    throw error(`${instr.op} not allowed during speculation`);
  }

  switch (instr.op) {
  case "const":
    // Interpret JSON numbers as either ints or floats.
    let value: Value;
    if (typeof instr.value === "number") {
      if (instr.type === "float")
        value = instr.value;
      else
        value = BigInt(Math.floor(instr.value))
    } else {
      value = instr.value;
    }

    state.env.set(instr.dest, value);
    return NEXT;

  case "id": {
    let val = getArgument(instr, state.env, 0);
    state.env.set(instr.dest, val);
    if (isPointer(val)) {
      if (state.refcounter.has_deadref((<Pointer> val).loc)) {
        throw error(`Tried to id freed pointer ${instr.args![0]}`);
      }
      state.refcounter.increment((<Pointer> val).loc)
    }
    return NEXT;
  }

  case "add": {
    let val = getInt(instr, state.env, 0) + getInt(instr, state.env, 1);
    val = BigInt.asIntN(64, val);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "mul": {
    let val = getInt(instr, state.env, 0) * getInt(instr, state.env, 1);
    val = BigInt.asIntN(64, val);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "sub": {
    let val = getInt(instr, state.env, 0) - getInt(instr, state.env, 1);
    val = BigInt.asIntN(64, val);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "div": {
    let val = getInt(instr, state.env, 0) / getInt(instr, state.env, 1);
    val = BigInt.asIntN(64, val);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "le": {
    let val = getInt(instr, state.env, 0) <= getInt(instr, state.env, 1);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "lt": {
    let val = getInt(instr, state.env, 0) < getInt(instr, state.env, 1);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "gt": {
    let val = getInt(instr, state.env, 0) > getInt(instr, state.env, 1);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "ge": {
    let val = getInt(instr, state.env, 0) >= getInt(instr, state.env, 1);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "eq": {
    let val = getInt(instr, state.env, 0) === getInt(instr, state.env, 1);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "not": {
    let val = !getBool(instr, state.env, 0);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "and": {
    let val = getBool(instr, state.env, 0) && getBool(instr, state.env, 1);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "or": {
    let val = getBool(instr, state.env, 0) || getBool(instr, state.env, 1);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "fadd": {
    let val = getFloat(instr, state.env, 0) + getFloat(instr, state.env, 1);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "fsub": {
    let val = getFloat(instr, state.env, 0) - getFloat(instr, state.env, 1);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "fmul": {
    let val = getFloat(instr, state.env, 0) * getFloat(instr, state.env, 1);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "fdiv": {
    let val = getFloat(instr, state.env, 0) / getFloat(instr, state.env, 1);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "fle": {
    let val = getFloat(instr, state.env, 0) <= getFloat(instr, state.env, 1);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "flt": {
    let val = getFloat(instr, state.env, 0) < getFloat(instr, state.env, 1);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "fgt": {
    let val = getFloat(instr, state.env, 0) > getFloat(instr, state.env, 1);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "fge": {
    let val = getFloat(instr, state.env, 0) >= getFloat(instr, state.env, 1);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "feq": {
    let val = getFloat(instr, state.env, 0) === getFloat(instr, state.env, 1);
    state.env.set(instr.dest, val);
    return NEXT;
  }

  case "print": {
    let args = instr.args || [];
    let values = args.map(i => get(state.env, i).toString());
    console.log(...values);
    return NEXT;
  }

  case "jmp": {
    return {"action": "jump", "label": getLabel(instr, 0)};
  }

  case "br": {
    let cond = getBool(instr, state.env, 0);
    if (cond) {
      return {"action": "jump", "label": getLabel(instr, 0)};
    } else {
      return {"action": "jump", "label": getLabel(instr, 1)};
    }
  }

  case "ret": {
    let args = instr.args || [];
    if (args.length == 0) {
      return {"action": "end", "ret": null};
    } else if (args.length == 1) {
      let val = get(state.env, args[0]);
      return {"action": "end", "ret": val};
    } else {
      throw error(`ret takes 0 or 1 argument(s); got ${args.length}`);
    }
  }

  case "nop": {
    return NEXT;
  }

  case "call": {
    return evalCall(instr, state);
  }

  case "alloc": {
    let amt = getInt(instr, state.env, 0);
    let typ = instr.type;
    if (!(typeof typ === "object" && typ.hasOwnProperty('ptr'))) {
      throw error(`cannot allocate non-pointer type ${instr.type}`);
    }
    let ptr = alloc(typ, Number(amt), state.heap);
    state.refcounter.increment(ptr.loc);
    state.env.set(instr.dest, ptr);
    return NEXT;
  }

  case "free": {
    let val = getPtr(instr, state.env, 0);
    state.heap.free(val.loc);
    state.refcounter.decrement(val.loc,true, "free");
    return NEXT;
  }

  case "store": {
    let target = getPtr(instr, state.env, 0);
    state.heap.write(target.loc, getArgument(instr, state.env, 1, target.type));
    return NEXT;
  }

  case "load": {
    let ptr = getPtr(instr, state.env, 0);
    let val = state.heap.read(ptr.loc);
    if (val === undefined || val === null) {
      throw error(`Pointer ${instr.args![0]} points to uninitialized data`);
    } else {
      state.env.set(instr.dest, val);
    }
    return NEXT;
  }

  case "ptradd": {
    let ptr = getPtr(instr, state.env, 0)
    let val = getInt(instr, state.env, 1)

    if (state.refcounter.has_deadref(ptr.loc)) {
      throw error(`Tried to ptradd freed pointer ${instr.args![0]}`);
    }

    let already_has_ptr = state.env.has(instr.dest);
    state.env.set(instr.dest, { loc: ptr.loc.add(Number(val)), type: ptr.type })

    if (!already_has_ptr) {
      // only increment if the variable was undeclared, otherwise we should
      // increment and decrement which cancel out
      state.refcounter.increment(ptr.loc);
    }

    return NEXT;
  }

  case "phi": {
    let labels = instr.labels || [];
    let args = instr.args || [];
    if (labels.length != args.length) {
      throw error(`phi node has unequal numbers of labels and args`);
    }
    if (!state.lastlabel) {
      throw error(`phi node executed with no last label`);
    }
    let idx = labels.indexOf(state.lastlabel);
    if (idx === -1) {
      // Last label not handled. Leave uninitialized.
      state.env.delete(instr.dest);
    } else {
      // Copy the right argument (including an undefined one).
      if (!instr.args || idx >= instr.args.length) {
        throw error(`phi node needed at least ${idx+1} arguments`);
      }
      let src = instr.args[idx];
      let val = state.env.get(src);
      if (val === undefined) {
        state.env.delete(instr.dest);
      } else {
        state.env.set(instr.dest, val);
      }
    }
    return NEXT;
  }

  // Begin speculation.
  case "speculate": {
    if (state.tracing) {finalizeTrace(state);}
    return {"action": "speculate"};
  }

  // Abort speculation if the condition is false.
  case "guard": {
    if (state.tracing) {error(`tracing during guard for state ${state}`)}
    if (getBool(instr, state.env, 0)) {
      return NEXT;
    } else {
      return {"action": "abort", "label": getLabel(instr, 0)};
    }
  }

  // Resolve speculation, making speculative state real.
  case "commit": {
    if (state.tracing) {error(`tracing during commit for state ${state}`)}
    return {"action": "commit"};
  }

  }
  unreachable(instr);
  throw error(`unhandled opcode ${(instr as any).op}`);
}


function evalFunc(func: bril.Function, state: State): Value | null {
  state.curlabel = 'entry';
  for (let i = 0; i < func.instrs.length; ++i) {
    let line = func.instrs[i];
    if (state.tracing && line) {
      state.instrs.push(line);
    }
    if ('op' in line) {
      // Run an instruction.
      let action = evalInstr(line, state);

      // Take the prescribed action.
      switch (action.action) {
      case 'end': {
        state.refcounter.cleanup_environment(state.env, action.ret);
        // Return from this function.
        return action.ret;
      }
      case 'speculate': {
        // Begin speculation.
        state.specparent = {...state};
        state.env = new Map(state.env);
        break;
      }
      case 'commit': {
        // Resolve speculation.
        if (!state.specparent) {
          throw error(`commit in non-speculative state`);
        }
        state.specparent = null;
        break;
      }
      case 'abort': {
        // Restore state.
        if (!state.specparent) {
          throw error(`abort in non-speculative state`);
        }
        // We do *not* restore `icount` from the saved state to ensure that we
        // count "aborted" instructions.
        Object.assign(state, {
          env: state.specparent.env,
          lastlabel: state.specparent.lastlabel,
          curlabel: state.specparent.curlabel,
          specparent: state.specparent.specparent,
        });
        break;
      }
      case 'next':
      case 'jump':
        break;
      default:
        unreachable(action);
        throw error(`unhandled action ${(action as any).action}`);
      }
      // Move to a label.
      if ('label' in action) {
        // Search for the label and transfer control.
        for (i = 0; i < func.instrs.length; ++i) {
          let sLine = func.instrs[i];
          if ('label' in sLine && sLine.label === action.label) {
            --i;  // Execute the label next.
            break;
          }
        }
        if (i === func.instrs.length) {
          throw error(`label ${action.label} not found`);
        }
      }
    } else if ('label' in line) {
      let fromblock = blockName(state);
      // Update CFG tracking for SSA phi nodes.
      state.lastlabel = state.curlabel;
      state.curlabel = line.label;
      let toblock = blockName(state);
      debugMessage(`Entered ${toblock}`);

      // Bail out if we're hitting a destination to a backedge
      // Either we started here (and should stop), or we didn't and should stop
      if (state.tracing && state.backedge_dests.has(toblock)) {
        debugMessage(`${toblock} is a backedge destination, so finalizing.`);
        finalizeTrace(state);
      }

      // Check for backedges
      let dominators = state.dom.get(fromblock);
      if (dominators && dominators.has(toblock)) {
        debugMessage(`${toblock} is a backedge!`);
        if (state.tracing) {
          if (toblock == state.trace_start) {
            debugMessage(`...We started here, so finalizing`);
            finalizeTrace(state);
          } else {
            debugMessage(`...We didn't start here, so abandoning`);
            state.backedge_dests.add(toblock);
            resetTrace(state);
          }
        } else if (!state.specparent) { // don't trace if we're speculating
          state.tracing = true;
          state.trace_start = toblock;
        }
      }

      // Push the block name for tracing
      if (state.tracing) {
        state.blocks.push(blockName(state));
      }
    }
  }

  // Reached the end of the function without hitting `ret`.
  if (state.specparent) {
    throw error(`implicit return in speculative state`);
  }
  state.refcounter.cleanup_environment(state.env, null);
  return null;
}

function parseBool(s: string): boolean {
  if (s === 'true') {
    return true;
  } else if (s === 'false') {
    return false;
  } else {
    throw error(`boolean argument to main must be 'true'/'false'; got ${s}`);
  }
}

function parseMainArguments(expected: bril.Argument[], args: string[]) : Env {
  let newEnv: Env = new Map();

  if (args.length !== expected.length) {
    throw error(`mismatched main argument arity: expected ${expected.length}; got ${args.length}`);
  }

  for (let i = 0; i < args.length; i++) {
    let type = expected[i].type;
    switch (type) {
      case "int":
        let n: bigint = BigInt(parseInt(args[i]));
        newEnv.set(expected[i].name, n as Value);
        break;
      case "bool":
        let b: boolean = parseBool(args[i]);
        newEnv.set(expected[i].name, b as Value);
        break;
    }
  }
  return newEnv;
}

function evalProg(prog: bril.Program, dom: Map<string, string[]>) {
  let heap = new Heap<Value>();
  let refcounter = new RefCounter(heap);
  let set_dom = domToSet(dom);
  let main = findFunc("main", prog.functions);
  if (main === null) {
    console.warn(`no main function defined, doing nothing`);
    return;
  }

  // Silly argument parsing to find the `-p` flag.
  let args: string[] = process.argv.slice(2, process.argv.length);
  let profiling = false;
  let pidx = args.indexOf('-p');
  if (pidx > -1) {
    profiling = true;
    args.splice(pidx, 1);
  }

  // Remaining arguments are for the main function.k
  let expected = main.args || [];
  let newEnv = parseMainArguments(expected, args);

  let state: State = {
    funcs: prog.functions,
    heap,
    refcounter: refcounter,
    env: newEnv,
    icount: BigInt(0),
    lastlabel: null,
    curlabel: null,
    specparent: null,

    tracing: false,
    dom: set_dom,
    backedge_dests: new Set<string>(),
    trace_start: null,
    curfunc: main,
    blocks: [],
    instrs: []
  }
  evalFunc(main, state);
  
  if (!heap.isEmpty()) {
    state.heap.log_heap();
    throw error(`Some memory locations have not been freed by end of execution.`);
  }

  if (profiling) {
    console.error(`total_dyn_inst: ${state.icount}`);
  }

}

async function main() {
  try {
    let prog = JSON.parse(await readStdin()) as bril.Program;
    let dom  = await callPython('/Users/aaron/projects/grad_school/cs6120/bril/compiler/dominators.py', JSON.stringify(prog));
    //debugMessage(`dominators: ${dom}`);
    evalProg(prog, dom);
  }
  catch(e) {
    if (e instanceof BriliError) {
      console.error(`error: ${e.message}`);
      process.exit(2);
    } else {
      throw e;
    }
  }
}

// Make unhandled promise rejections terminate.
process.on('unhandledRejection', e => { throw e });

main();
