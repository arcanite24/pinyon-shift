// Repairs the control flow Ghidra cuts at the register save/restore helpers
// (NL-2.2). ShiftGlue splits each __savegprlr_N / __savefpr_N style helper
// into one function a register, every entry falling through into the next,
// so most of them have no return of their own. Ghidra's "Non-Returning
// Functions - Discovered" analyzer then marks them non-returning, and every
// function that calls one in its prologue ends after that call: its body is
// cut to the first instructions, its callees and callers go missing and the
// rest is typed as data.
//
// This script, run headless after ApplyPinyonKnowledge with -noanalysis:
//   1. clears the non-returning flag of every function whose last
//      instruction falls through into another function's start;
//   2. at each call to such a function, clears the tail-call override,
//      clears data at the return address and disassembles from there;
//   3. recomputes every function's body from the restored flow;
//   4. extends bodies past undecodable VMX128 words up to the next start.
//@category Pinyon

import java.util.ArrayList;
import java.util.List;

import ghidra.app.cmd.function.CreateFunctionCmd;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.FlowOverride;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.symbol.Reference;

public class RepairHelperFlow extends GhidraScript {
  @Override
  public void run() throws Exception {
    Listing listing = currentProgram.getListing();
    List<Function> helpers = new ArrayList<>();
    FunctionIterator all = listing.getFunctions(true);
    while (all.hasNext()) {
      Function fn = all.next();
      // Selected by the fall-through alone, so a second run still repairs
      // the call sites after an earlier one cleared the flag.
      Instruction last = listing.getInstructionContaining(fn.getBody().getMaxAddress());
      if (last == null) continue;
      Address next = last.getFallThrough();
      if (next != null && getFunctionAt(next) != null) {
        if (fn.hasNoReturn()) fn.setNoReturn(false);
        helpers.add(fn);
      }
    }

    int returns = 0, cleared = 0, overrides = 0;
    for (Function helper : helpers) {
      if (monitor.isCancelled()) break;
      for (Reference ref : getReferencesTo(helper.getEntryPoint())) {
        if (!ref.getReferenceType().isCall()) continue;
        Instruction call = listing.getInstructionAt(ref.getFromAddress());
        if (call == null) continue;
        // Analysis also turned the call into a tail call (flow override
        // CALL_RETURN), which ends the caller's body at the call.
        if (call.getFlowOverride() == FlowOverride.CALL_RETURN) {
          call.setFlowOverride(FlowOverride.NONE);
          overrides++;
        }
        if (call.isFallThroughOverridden()) {
          call.clearFallThroughOverride();
          overrides++;
        }
        Address after = call.getMaxAddress().next();
        if (after == null || listing.getInstructionAt(after) != null) continue;
        Data data = listing.getDefinedDataContaining(after);
        if (data != null) {
          clearListing(data.getMinAddress(), data.getMaxAddress());
          cleared++;
        }
        disassemble(after);
        returns++;
      }
    }

    int fixed = 0;
    all = listing.getFunctions(true);
    while (all.hasNext()) {
      if (monitor.isCancelled()) break;
      Function fn = all.next();
      long before = fn.getBody().getNumAddresses();
      CreateFunctionCmd.fixupFunctionBody(currentProgram, fn, monitor);
      if (fn.getBody().getNumAddresses() != before) fixed++;
    }
    // 4. Ghidra's PowerPC language doesn't decode VMX128, so flow stops at the
    // first such instruction. ShiftGlue's starts bound each function, so
    // disassemble what follows up to the next start and add those
    // instructions to the body: calls and references past a vector
    // instruction then show up in xref and caller queries.
    int extended = 0, undecoded = 0;
    List<Function> ordered = new ArrayList<>();
    all = listing.getFunctions(true);
    while (all.hasNext()) ordered.add(all.next());
    for (int k = 0; k + 1 < ordered.size(); k++) {
      if (monitor.isCancelled()) break;
      Function fn = ordered.get(k);
      Address entry = fn.getEntryPoint();
      Address end = ordered.get(k + 1).getEntryPoint().previous();
      if (end == null || end.compareTo(entry) <= 0 || fn.getBody().contains(end)) continue;
      if (end.subtract(entry) > 0x40000) continue;  // not a ShiftGlue neighbour
      AddressSet body = new AddressSet(fn.getBody());
      boolean grew = false;
      for (Address a = fn.getBody().getMaxAddress().next(); a != null && a.compareTo(end) <= 0; a = a.add(4)) {
        if (listing.getInstructionAt(a) == null && listing.getDefinedDataContaining(a) == null) {
          disassemble(a);
        }
        Instruction insn = listing.getInstructionAt(a);
        if (insn == null) {
          undecoded++;
          continue;
        }
        Function owner = getFunctionContaining(a);
        if (owner == null || owner == fn) {
          body.add(insn.getMinAddress(), insn.getMaxAddress());
          grew = true;
        }
      }
      if (!grew) continue;
      try {
        fn.setBody(body);
        extended++;
      } catch (Exception e) {
        // Overlaps another function's body; leave this one as analysed.
      }
    }

    println(String.format("RepairHelperFlow: %d fall-through helpers made returning, %d call returns "
        + "disassembled (%d over data cleared), %d call flow overrides cleared, %d function bodies changed, "
        + "%d extended to the next ShiftGlue start (%d undecodable words)",
        helpers.size(), returns, cleared, overrides, fixed, extended, undecoded));
  }
}
