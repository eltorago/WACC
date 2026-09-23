"""Native Tk review adapter. Analysis and decisions use the same services as the CLI."""
import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from . import ENGINE_VERSION, corpus, service, store, reports
from .contracts import PolicyError, REVIEWED


class Desktop(ttk.Frame):
    def __init__(self, master, assessment=None):
        super().__init__(master, padding=12)
        self.pack(fill="both", expand=True)
        self.path = None
        self.state = None
        self.busy = False
        self.cancel = threading.Event()
        self.messages = queue.Queue()
        master.title("WACC — Policy coverage review (pilot)")
        master.geometry("1350x850")
        master.minsize(1000, 650)
        master.protocol("WM_DELETE_WINDOW", self.close)
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        for label, command in [("New assessment", self.new), ("Open", self.open), ("New analysis run", self.new_run),
                               ("Save snapshot", self.snapshot), ("Finalise snapshot", self.finalise), ("Export report", self.export),
                               ("Cancel analysis", self.cancel.set)]:
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=(0, 6))
        self.status = tk.StringVar(value="Open an assessment or select New assessment. Use Framework updates to prepare missing sources.")
        ttk.Label(self, textvariable=self.status, wraplength=1250).pack(fill="x", pady=10)
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)
        self.pages = {}
        for title in ("Overview", "Requirements", "Potential gaps", "Documents", "Framework relationships", "Reports", "History", "Framework updates", "Settings"):
            frame = ttk.Frame(self.tabs, padding=10)
            self.tabs.add(frame, text=title)
            self.pages[title] = frame
        self.overview = ScrolledText(self.pages["Overview"], wrap="word", height=18)
        self.overview.pack(fill="both", expand=True)
        self.chart = tk.Canvas(self.pages["Overview"], height=100, highlightthickness=0)
        self.chart.pack(fill="x")
        self.framework_totals = self.tree(self.pages['Overview'], ('Framework', 'In scope', 'Reviewed', 'Confirmed coverage', 'Automatically assessed'))
        self.framework_totals.configure(height=4)
        filters = ttk.Frame(self.pages["Requirements"])
        filters.pack(fill="x")
        ttk.Label(filters, text="Search requirements").pack(side="left")
        self.search = tk.StringVar()
        ttk.Entry(filters, textvariable=self.search).pack(side="left", fill="x", expand=True, padx=8)
        self.filter = tk.StringVar(value="All")
        ttk.Combobox(filters, textvariable=self.filter, state="readonly", values=("All", "Pending", "Reviewed", "NeedsReReview", *service.AUTOMATED), width=22).pack(side="left")
        self.search.trace_add("write", lambda *_: self.filter_rows())
        self.filter.trace_add("write", lambda *_: self.filter_rows())
        panes = ttk.Panedwindow(self.pages["Requirements"], orient="horizontal")
        panes.pack(fill="both", expand=True, pady=(10, 0))
        left, right = ttk.Frame(panes), ttk.Frame(panes)
        panes.add(left, weight=2)
        panes.add(right, weight=3)
        self.requirements = self.tree(left, ("Reference", "Automated", "Review"))
        self.requirements.configure(show='tree headings')
        self.requirements.heading('#0', text='Framework / section')
        self.requirements.column('#0', width=180, minwidth=100)
        self.requirements.bind("<<TreeviewSelect>>", self.select_requirement)
        self.detail = ScrolledText(right, wrap="word", height=12)
        self.detail.pack(fill="both", expand=True)
        ttk.Label(right, text="Evidence passages — select to inspect exact text and recorded rule checks").pack(anchor="w", pady=4)
        self.evidence = ttk.Combobox(right, state="readonly")
        self.evidence.pack(fill="x")
        self.evidence.bind("<<ComboboxSelected>>", self.show_evidence)
        self.passage = ScrolledText(right, wrap="word", height=9)
        self.passage.pack(fill="both", expand=True)
        self.passage.tag_configure("match", background="#ffe394", foreground="#182229")
        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=6)
        ttk.Button(actions, text="Review finding / confirm / reject", command=self.review).pack(side="left")
        ttk.Button(actions, text="Related evidence and frameworks", command=self.relationships).pack(side="left", padx=8)
        self.gaps = self.tree(self.pages["Potential gaps"], ("Reference", "Missing obligations", "Status"))
        self.gaps.bind("<<TreeviewSelect>>", self.open_gap)
        self.doc_tree = self.tree(self.pages["Documents"], ("File", "Status", "Approval", "Retained / extracted passages"))
        self.doc_tree.bind("<<TreeviewSelect>>", self.show_document)
        self.doc_text = ScrolledText(self.pages["Documents"], height=14, wrap="word")
        self.doc_text.pack(fill="both", expand=True)
        ttk.Button(self.pages["Documents"], text="Open original after hash check", command=self.open_original).pack(anchor="w")
        self.graph = tk.Canvas(self.pages["Framework relationships"], height=180, background="white")
        self.graph.pack(fill="x")
        self.edges = self.tree(self.pages["Framework relationships"], ("Source", "Relationship", "Target", "Evidence relation"))
        self.graph_status = tk.StringVar(value="Choose a requirement to see its bounded neighbourhood.")
        ttk.Label(self.pages["Framework relationships"], textvariable=self.graph_status).pack(anchor="w")
        ttk.Label(self.pages["Reports"], text="Export the selected saved run as JSON, CSV, Markdown or self-contained HTML.\nSummary-only omits evidence excerpts; the saved assessment remains sensitive.\nExporting does not finalise or approve the assessment.", wraplength=900).pack(anchor="w", pady=10)
        ttk.Button(self.pages["Reports"], text="Export report", command=self.export).pack(anchor="w")
        self.history = self.tree(self.pages["History"], ("Run", "Created"))
        self.history.bind("<<TreeviewSelect>>", self.open_history)
        self.history_text = ScrolledText(self.pages["History"], height=12, wrap="word")
        self.history_text.pack(fill="both", expand=True)
        self.settings = ScrolledText(self.pages["Settings"], wrap="word")
        self.settings.pack(fill="both", expand=True)
        update_page = self.pages['Framework updates']
        ttk.Label(update_page, text='Download current framework files from their publishers. This action needs internet access; analysis and saved assessments work offline.', wraplength=1000).pack(anchor='w', pady=8)
        self.update_choices = {key:tk.BooleanVar(value=True) for key in corpus.REVIEW_FRAMEWORKS}
        for key, variable in self.update_choices.items():
            ttk.Checkbutton(update_page, text=corpus.REVIEW_FRAMEWORKS[key], variable=variable).pack(anchor='w')
        ttk.Button(update_page, text='Download updates', command=self.update_frameworks).pack(anchor='w', pady=8)
        ttk.Label(update_page, text='If a publisher blocks automatic access, download its file yourself and select one framework above before importing it.', wraplength=1000).pack(anchor='w')
        ttk.Button(update_page, text='Import framework file', command=lambda:self.update_frameworks(True)).pack(anchor='w', pady=8)
        self.update_text = ScrolledText(update_page, wrap='word')
        self.update_text.pack(fill='both', expand=True)
        try:
            installed = corpus.installed()
        except PolicyError as error:
            installed = {'status': str(error), 'historicalAssessments': 'Can still be opened without the corpus.'}
        self.set_text(self.settings, "Engine " + ENGINE_VERSION + "\n\nNo listener, telemetry or AI inference. Framework downloads occur only through the explicit update action.\n\nDesktop retention defaults to extracted text for manual review. Original files are not embedded.\n\nAssessment files are ordinary, unencrypted SQLite databases. Store them in an approved local folder.\n\nCorpus: " + json.dumps(installed, ensure_ascii=False, indent=2))
        master.bind("<Control-o>", lambda _: self.open())
        master.bind("<Control-n>", lambda _: self.new())
        master.bind("<Control-s>", lambda _: self.snapshot())
        master.after(100, self.poll)
        if assessment:
            self.load(assessment)

    @staticmethod
    def tree(parent, columns):
        box = ttk.Frame(parent)
        box.pack(fill="both", expand=True)
        tree = ttk.Treeview(box, columns=columns, show="headings", selectmode="browse")
        for name in columns:
            tree.heading(name, text=name)
            tree.column(name, width=170, minwidth=80)
        bar = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(box, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=bar.set, xscrollcommand=horizontal.set)
        tree.grid(row=0,column=0,sticky='nsew')
        bar.grid(row=0,column=1,sticky='ns')
        horizontal.grid(row=1,column=0,sticky='ew')
        box.rowconfigure(0,weight=1)
        box.columnconfigure(0,weight=1)
        return tree

    @staticmethod
    def set_text(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def guarded(self, action):
        try:
            return action()
        except PolicyError as error:
            messagebox.showerror("WACC", str(error), parent=self)
        except Exception:
            messagebox.showerror("WACC", "The operation could not complete. Saved work is unchanged; check workspace permissions.", parent=self)

    def load(self, path, run=None):
        state = self.guarded(lambda: store.load(path, run))
        if state:
            self.path, self.state = str(path), state
            self.refresh()

    def open(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(parent=self, filetypes=[("WACC assessment", "*.wacc")])
        if path:
            self.load(path)

    def new_run(self):
        if self.state:
            self.new(self.path)

    def new(self, destination=None):
        if self.busy:
            return
        available = corpus.installed()
        choices = {f['id']: f for f in available['availableFrameworks'] if f['id'] in corpus.REVIEW_FRAMEWORKS}
        if not choices:
            messagebox.showerror('Frameworks unavailable', 'Prepare a local WA CSP, ASD ISM or AESCSF source collection before creating an assessment.', parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Select assessment scope")
        dialog.geometry("780x750")
        form = ttk.Frame(dialog, padding=18)
        form.pack(fill="both", expand=True)
        values = {}
        defaults = dict(Name="Policy assessment", Organisation="", Scope="", Approval="unknown", Retention="extracted")
        if self.state and destination:
            defaults.update(Name=self.state["run"]["name"], Organisation=self.state["run"].get("organisation", ""), Scope=self.state["run"]["scope"]["description"])
        for label, default in defaults.items():
            ttk.Label(form, text=label).pack(anchor="w", pady=(8, 0))
            values[label] = tk.StringVar(value=default)
            if label in ("Approval", "Retention"):
                options = ("unknown", "approved", "draft", "superseded") if label == "Approval" else ("evidence", "extracted")
                ttk.Combobox(form, textvariable=values[label], values=options, state="readonly").pack(fill="x")
            else:
                ttk.Entry(form, textvariable=values[label]).pack(fill="x")
        ttk.Label(form, text='Frameworks to assess — select one or more', wraplength=700).pack(anchor='w', pady=10)
        previous = {f['id'] for f in self.state['run']['versions']['frameworks']} if self.state and destination else {next(iter(choices))}
        selected_frameworks = {key: tk.BooleanVar(value=key in previous and key in choices) for key in corpus.REVIEW_FRAMEWORKS}
        for key, variable in selected_frameworks.items():
            label = corpus.REVIEW_FRAMEWORKS[key]
            label += ' — ' + choices[key]['edition'] if key in choices else ' — local source unavailable'
            ttk.Checkbutton(form, text=label, variable=variable, state='normal' if key in choices else 'disabled').pack(anchor='w')
        selected = tk.Listbox(form, height=5, selectmode="extended")
        selected.pack(fill="both", expand=True, pady=8)
        def add():
            for path in filedialog.askopenfilenames(parent=dialog, filetypes=[("Policy documents", "*.pdf *.docx *.txt *.md")]):
                if path not in selected.get(0, "end"):
                    selected.insert("end", path)
        def remove():
            for index in reversed(selected.curselection()):
                selected.delete(index)
        buttons = ttk.Frame(form)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Add documents", command=add).pack(side="left")
        ttk.Button(buttons, text="Exclude selected", command=remove).pack(side="left", padx=8)
        ttk.Label(form, text="Evidence mode stores matched passages. Extracted mode stores all text and supports wider manual inspection. Neither mode embeds original files.", wraplength=700).pack(anchor="w", pady=8)
        def run():
            frameworks = [key for key, variable in selected_frameworks.items() if variable.get()]
            if not frameworks:
                messagebox.showerror('Choose a framework', 'Select at least one framework to assess.', parent=dialog)
                return
            if not values["Scope"].get().strip() or not selected.size():
                messagebox.showerror("Scope required", "Describe the scope and select at least one document.", parent=dialog)
                return
            path = destination or filedialog.asksaveasfilename(parent=dialog, defaultextension=".wacc", filetypes=[("WACC assessment", "*.wacc")])
            if not path:
                return
            options = dict(paths=list(selected.get(0, "end")), name=values["Name"].get(), scope=values["Scope"].get(),
                           organisation=values["Organisation"].get(), approval=values["Approval"].get(), retention=values["Retention"].get(),
                           framework=frameworks[0], also=frameworks[1:])
            dialog.destroy()
            self.start_analysis(path, options)
        ttk.Button(form, text="Analyse and save", command=run).pack(anchor="e", pady=10)

    def start_analysis(self, path, options):
        self.busy = True
        self.cancel.clear()
        self.status.set("Extracting documents and evaluating rules… Cancel analysis leaves saved runs unchanged.")
        def work():
            try:
                run = service.analyse(cancel=self.cancel, **options)
                if self.cancel.is_set():
                    raise KeyboardInterrupt
                store.save(path, run)
                self.messages.put(("complete", path))
            except KeyboardInterrupt:
                self.messages.put(("error", "Analysis cancelled; previous saved work is unchanged."))
            except PolicyError as error:
                self.messages.put(("error", str(error)))
            except Exception:
                self.messages.put(("error", "Analysis failed. Check document format and folder permissions; previous saved work is unchanged."))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == 'update-progress':
                    self.status.set(value)
                    continue
                self.busy = False
                if kind == "complete":
                    self.load(value)
                elif kind == 'framework-updated':
                    self.status.set('Framework update finished. New analyses use the updated files; saved runs retain their original versions.')
                    self.set_text(self.update_text, '\n\n'.join(r['framework'] + ': ' + r['status'] + '\n' +
                        (r.get('message') or str(r['requirements']) + ' requirements · ' + r['edition']) for r in value))
                    self.set_text(self.settings, 'Installed framework collection\n\n' + json.dumps(corpus.installed(),ensure_ascii=False,indent=2))
                else:
                    self.status.set(value)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self.poll)

    def update_frameworks(self, manual=False):
        if self.busy:
            return
        selected = [key for key, value in self.update_choices.items() if value.get()]
        if not selected or (manual and len(selected) != 1):
            messagebox.showerror('Choose frameworks', 'Select one framework for manual import, or one or more for downloads.', parent=self)
            return
        path = None
        if manual:
            path = filedialog.askopenfilename(parent=self, filetypes=[('Publisher frameworks','*.pdf *.xlsx *.json')])
            if not path:
                return
        self.busy = True
        self.status.set('Updating the local framework collection…')
        def work():
            try:
                from .updates import update
                result = update(selected, path, progress=lambda value:self.messages.put(('update-progress',value)))
                self.messages.put(('framework-updated',result))
            except Exception:
                self.messages.put(('error','Framework update could not finish. Saved assessments are unchanged; check local folder access.'))
        threading.Thread(target=work,daemon=True).start()

    def refresh(self):
        run = self.state["run"]
        totals = service.summary(run, self.state["events"])
        state_label = 'Historical run (read-only)' if self.state['metadata']['historical'] else 'Finalised' if self.state['metadata']['selectedFinalised'] else 'Working review'
        self.status.set(run["name"] + " | " + run["scope"]["description"] + " | " + run["scope"]["mode"] + " | " + state_label)
        def percent(value):
            return 'N/A' if value['percent'] is None else '%.1f%% (%s / %s)' % (value['percent'],format(value['numerator'],'.2f').rstrip('0').rstrip('.'),value['denominator'])
        labels={'FullCandidate':'Full evidence candidates','PartialCandidate':'Partial evidence candidates','NoEvidenceFound':'No qualifying evidence found','Ambiguous':'Ambiguous findings','NotAssessed':'Not assessed'}
        overview = [run['name'], 'Scope: ' + run['scope']['description'] + ' (' + run['scope']['mode'] + ')',
                    'Baseline: ' + '; '.join(f['edition'] for f in run['versions']['frameworks']),
                    '', '%d selected documents; %d extracted successfully; %d with extraction issues' %
                    (len(run['documents']),sum(d['status']=='Ready' for d in run['documents']),sum(d['status']!='Ready' for d in run['documents'])),
                    '%d requirements in scope; %d excluded' % (totals['inScope'],totals['excluded']),
                    '%d of %d requirements reviewed' % (totals['reviewed'],totals['reviewable']), '']
        overview += [labels[k] + ': ' + str(v) for k,v in totals['automatedCounts'].items()]
        overview += ['', 'Assessment completeness: ' + percent(totals['assessmentCompleteness']),
                     'Evidence coverage within the computable subset only: ' + percent(totals['assessedScopeCoverage']),
                     'Reviewer-confirmed evidence floor across the full scope: ' + percent(totals['confirmedEvidenceFloor']),
                     '', 'Next: review ambiguous evidence and extraction issues, then assess requirements without an automated rule.',
                     '', *run['limitations'], '', 'Corpus: ' + run['versions']['corpus'], 'Run: ' + run['runId']]
        self.set_text(self.overview, '\n'.join(overview))
        self.framework_totals.delete(*self.framework_totals.get_children())
        for f in service.framework_summaries(run, self.state['events']):
            self.framework_totals.insert('', 'end', values=(corpus.REVIEW_FRAMEWORKS.get(f['id'], f['title']),
                f['inScope'], str(f['reviewed']) + ' / ' + str(f['reviewable']), percent(f['confirmedEvidenceFloor']),
                str(f['computable']) + ' / ' + str(f['inScope'])))
        self.chart.delete("all")
        colors = ("#266b47", "#b38519", "#94665c", "#8463a5", "#8b939c")
        start, width = 10, max(850, self.chart.winfo_width()-20)
        for index, (status, count) in enumerate(totals["automatedCounts"].items()):
            end = start + width * count / max(1, totals["inScope"])
            self.chart.create_rectangle(start, 8, end, 34, fill=colors[index], outline="white")
            self.chart.create_text(10 + index*220, 60, text=status + ": " + str(count), anchor="w", fill="black")
            start = end
        self.filter_rows()
        self.gaps.delete(*self.gaps.get_children())
        for r in service.apply_reviews(run, self.state["events"]):
            if r["missingObligations"] and r["applicability"] != "NotApplicable":
                self.gaps.insert("", "end", iid=r["id"], values=(r["id"], ", ".join(r["missingObligations"]), r["automatedFinding"]))
        self.doc_tree.delete(*self.doc_tree.get_children())
        for d in run["documents"]:
            self.doc_tree.insert("", "end", iid=d["id"], values=(d["name"], d["status"], d["approvalStatus"], "%d / %d" % (len(d["passages"]), d.get("extractedPassageCount", len(d["passages"])))))
        self.history.delete(*self.history.get_children())
        for h in self.state["history"]:
            self.history.insert("", "end", iid=h["id"], values=(h["id"], h["createdAt"]))
        self.set_text(self.history_text, json.dumps(self.state["events"], ensure_ascii=False, indent=2))

    def filter_rows(self):
        if not self.state:
            return
        self.requirements.delete(*self.requirements.get_children())
        for r in service.apply_reviews(self.state["run"], self.state["events"]):
            if self.search.get().casefold() not in (r["id"] + r["heading"] + r["authoritativeText"]).casefold():
                continue
            if self.filter.get() != "All" and self.filter.get() not in (r["automatedFinding"], r["reviewState"]):
                continue
            group = 'group/' + r['frameworkId'] + '/' + str(r['parentId'])
            if not self.requirements.exists(group):
                self.requirements.insert('', 'end', iid=group, text=r['frameworkId'] + ' / ' + str(r['parentId']) + ' ' + r['heading'], open=True)
            self.requirements.insert(group, "end", iid=r["id"], values=(r["officialReference"], r["automatedFinding"], r["reviewState"]))

    def current(self):
        selected = self.requirements.selection()
        return next((r for r in service.apply_reviews(self.state["run"], self.state["events"]) if selected and r["id"] == selected[0]), None) if self.state else None

    def select_requirement(self, _=None):
        r = self.current()
        if not r:
            return
        self.set_text(self.detail, r["id"] + " — " + r["heading"] + "\n" + r["context"] + "\n" + r["authoritativeText"] +
                      "\n\nAutomated: " + r["automatedFinding"] + "; review: " + r["reviewState"] + " / " + str(r["reviewerFinding"]) +
                      "\n\n" + "\n".join(a["interpretation"] + " [" + a["reviewStatus"] + "] — " + next(x["state"] for x in r["atomResults"] if x["id"] == a["id"]) for a in r["obligations"]) +
                      "\n\nFlags: " + ", ".join(r["flags"]))
        if r.get('review'):
            self.set_text(self.detail, self.detail.get('1.0','end') + '\nReviewer decision: ' + r['review']['finding'] +
                          '\nReason: ' + r['review']['reason'] + '\n' + r['review'].get('comment','') +
                          '\n\nManually linked evidence:\n' + '\n\n'.join(e['excerpt'] + '\n' + json.dumps(e['locator']) for e in r['review'].get('manualEvidence',[])))
        self.evidence.configure(values=[e["obligationId"] + " | " + e["state"] + " | " + json.dumps(e["locator"]) for e in r["evidence"]])
        self.evidence.set("")
        self.set_text(self.passage, "No qualifying evidence was identified in the selected documents." if not r["evidence"] else "Select a passage above.")
        if r["evidence"]:
            self.evidence.current(0)
            self.show_evidence()

    def show_evidence(self, _=None):
        r = self.current()
        index = self.evidence.current()
        if not r or index < 0:
            return
        e = r["evidence"][index]
        self.set_text(self.passage, e["excerpt"] + "\n\nSource: " + e["documentHash"] + "\n" + json.dumps(e["locator"]) +
                      "\nRule " + e["ruleVersion"] + "; " + e["context"] + "\n" + json.dumps(e["checks"], ensure_ascii=False, indent=2))
        self.passage.tag_remove("match", "1.0", "end")
        for span in e["matchedSpans"]:
            self.passage.tag_add("match", "1.0 + %d chars" % span["start"], "1.0 + %d chars" % span["end"])

    def open_gap(self, _=None):
        selection = self.gaps.selection()
        if selection:
            self.search.set("")
            self.filter.set("All")
            self.requirements.selection_set(selection[0])
            self.requirements.see(selection[0])
            self.tabs.select(self.pages["Requirements"])

    def review(self):
        r = self.current()
        if not r:
            return
        dialog = tk.Toplevel(self)
        dialog.title("Review " + r["id"])
        dialog.geometry("850x760")
        box = ttk.Frame(dialog, padding=16)
        box.pack(fill="both", expand=True)
        fields = {}
        for title in ("Reviewer", "Finding", "Reason"):
            ttk.Label(box, text=title).pack(anchor="w", pady=(8, 0))
            fields[title] = tk.StringVar(value="NotAssessed" if title == "Finding" else "")
            widget = ttk.Combobox(box, textvariable=fields[title], values=REVIEWED, state="readonly") if title == "Finding" else ttk.Entry(box, textvariable=fields[title])
            widget.pack(fill="x")
        ttk.Label(box, text="Select the obligations you have confirmed (Ctrl or Shift for multiple)").pack(anchor="w", pady=8)
        atoms = tk.Listbox(box, selectmode="extended", exportselection=False, height=5)
        atoms.pack(fill="x")
        for a in r["obligations"]:
            atoms.insert("end", a["id"] + " — " + a["interpretation"])
        ttk.Label(box, text="Select accepted evidence; leave rejected evidence unselected").pack(anchor="w", pady=8)
        evidence = tk.Listbox(box, selectmode="extended", exportselection=False, height=5)
        evidence.pack(fill="x")
        for e in r["evidence"]:
            evidence.insert("end", e["state"] + " — " + e["excerpt"][:150])
        manual = []
        def link_passage():
            selected_atoms = atoms.curselection()
            if not selected_atoms:
                messagebox.showerror('Choose an obligation', 'Select an obligation above before linking a passage.', parent=dialog)
                return
            chooser = tk.Toplevel(dialog)
            chooser.title('Link retained source passage')
            chooser.geometry('950x500')
            choices = [(d, p) for d in self.state['run']['documents'] if d['included'] for p in d['passages']]
            passages = tk.Listbox(chooser, exportselection=False)
            passages.pack(fill='both', expand=True)
            for d,p in choices:
                passages.insert('end', d['name'] + ' | ' + json.dumps(p['locator']) + ' | ' + p['text'][:250])
            ttk.Label(chooser, text='Only retained passages are shown. Use a new run with extracted-text retention to inspect other passages.', wraplength=900).pack()
            def choose():
                if passages.curselection():
                    d,p = choices[passages.curselection()[0]]
                    for i in selected_atoms:
                        manual.append(dict(documentId=d['id'], passageId=p['id'], obligationId=r['obligations'][i]['id']))
                    chooser.destroy()
            ttk.Button(chooser, text='Link selected passage to selected obligations', command=choose).pack(pady=8)
        ttk.Button(box, text='Link another retained passage', command=link_passage).pack(anchor='w', pady=6)
        ttk.Label(box, text="Comment / manual review notes").pack(anchor="w", pady=8)
        comment = ScrolledText(box, height=6)
        comment.pack(fill="both", expand=True)
        def save():
            def perform():
                event = service.review_event(self.state["run"], r["id"], fields["Finding"].get(), fields["Reason"].get(), fields["Reviewer"].get(),
                                             [r["obligations"][i]["id"] for i in atoms.curselection()], [r["evidence"][i]["id"] for i in evidence.curselection()], comment.get("1.0", "end").strip(), manual)
                store.append_review(self.path, event)
                dialog.destroy()
                self.load(self.path)
            self.guarded(perform)
        ttk.Button(box, text="Save reviewer decision", command=save).pack(anchor="e", pady=10)

    def show_document(self, _=None):
        ids = self.doc_tree.selection()
        if not ids:
            return
        d = next(d for d in self.state["run"]["documents"] if d["id"] == ids[0])
        self.set_text(self.doc_text, "Extracted text — not original page layout\n" + json.dumps({k:v for k,v in d.items() if k != "passages"}, indent=2, ensure_ascii=False) +
                      "\n\n" + "\n\n".join(json.dumps(p["locator"]) + "\n" + p["text"] for p in d["passages"]))

    def open_original(self):
        ids = self.doc_tree.selection()
        if not ids:
            return
        check = next(s for s in store.verify_sources(self.state) if s["documentId"] == ids[0])
        if check["status"] != "Unchanged":
            messagebox.showerror("Source unavailable", check["status"], parent=self)
            return
        doc = next(d for d in self.state["run"]["documents"] if d["id"] == ids[0])
        self.guarded(lambda: os.startfile(doc["path"]))

    def relationships(self):
        r = self.current()
        if not r:
            return
        graph = service.neighbourhood(self.state["run"], r["id"])
        self.edges.delete(*self.edges.get_children())
        self.graph.delete("all")
        for index, edge in enumerate(graph["edges"]):
            self.edges.insert("", "end", values=(edge["source"], edge["relationship"], edge["target"], edge["relation"]))
            if index < 4:
                y = 20 + index*38
                self.graph.create_text(10, y, text=edge["source"][:54], anchor="w")
                self.graph.create_line(400, y, 700, y, arrow="last", dash=(4, 2) if edge["relation"] == "MappedOnly" else ())
                self.graph.create_text(540, y-10, text=edge["relationship"])
                self.graph.create_text(710, y, text=edge["target"][:54], anchor="w")
        self.graph_status.set("%d relationships; diagram shows the first four. Table limit: 50. %s" % (graph["total"], "Results truncated." if graph["truncated"] else ""))
        self.tabs.select(self.pages["Framework relationships"])

    def open_history(self, _=None):
        ids = self.history.selection()
        if ids and ids[0] != self.state["run"]["runId"]:
            self.load(self.path, ids[0])

    def snapshot(self):
        if not self.path:
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".wacc", filetypes=[("WACC assessment", "*.wacc")])
        if path:
            self.guarded(lambda: store.snapshot(self.path, path))

    def finalise(self):
        if self.path and messagebox.askyesno("Finalise snapshot", "Lock the current run against further review? Unreviewed requirements will remain unreviewed. A new analysis creates a new revision.", parent=self):
            self.guarded(lambda: store.finalise(self.path,self.state['run']['runId']))
            self.load(self.path)

    def export(self):
        if not self.state:
            return
        dialog = tk.Toplevel(self)
        dialog.title('Choose report frameworks')
        box = ttk.Frame(dialog, padding=20)
        box.pack(fill='both', expand=True)
        ttk.Label(box, text='Include these frameworks in the report:').pack(anchor='w', pady=8)
        selected = {}
        for f in self.state['run']['versions']['frameworks']:
            selected[f['id']] = tk.BooleanVar(value=True)
            ttk.Checkbutton(box, text=corpus.REVIEW_FRAMEWORKS.get(f['id'], f['title']), variable=selected[f['id']]).pack(anchor='w')
        full = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text='Include evidence excerpts and review notes', variable=full).pack(anchor='w', pady=12)
        def save():
            frameworks = [key for key, value in selected.items() if value.get()]
            if not frameworks:
                messagebox.showerror('Choose a framework', 'Select at least one framework.', parent=dialog)
                return
            path = filedialog.asksaveasfilename(parent=dialog, defaultextension='.html', filetypes=[('HTML','*.html'),('JSON','*.json'),('CSV','*.csv'),('Markdown','*.md')])
            if path:
                format = {'.md':'markdown','.html':'html','.csv':'csv','.json':'json'}.get(Path(path).suffix.lower(),'html')
                def perform():
                    reports.export_report(self.state,path,format,full.get(),True,self.path,frameworks)
                    dialog.destroy()
                self.guarded(perform)
        ttk.Button(box, text='Save report', command=save).pack(anchor='e', pady=8)

    def close(self):
        if self.busy:
            self.cancel.set()
            self.status.set("Cancelling analysis before closing…")
            self.after(150, self.close)
        else:
            self.master.destroy()


def launch(assessment=None):
    root = tk.Tk()
    Desktop(root, assessment)
    root.mainloop()
