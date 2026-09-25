"""Native framework alignment workspace, backed by the shared comparison service."""
import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from . import ENGINE_VERSION, alignment, corpus, service, store, reports
from .contracts import PolicyError


class Desktop(ttk.Frame):
    def __init__(self, master, assessment=None):
        super().__init__(master, padding=12)
        self.pack(fill="both", expand=True)
        self.path = None
        self.state = None
        self.busy = False
        self.cancel = threading.Event()
        self.messages = queue.Queue()
        master.title("WACC — Framework alignment")
        master.geometry("1350x850")
        master.minsize(1000, 650)
        master.protocol("WM_DELETE_WINDOW", self.close)
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        for label, command in [("New comparison", self.new), ("Open", self.open), ("Compare new documents", self.new_run),
                               ("Save a copy", self.snapshot), ("Export report", self.export),
                               ("Cancel analysis", self.cancel.set)]:
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=(0, 6))
        self.status = tk.StringVar(value="Open a saved comparison or select New comparison. Use Framework updates to prepare missing sources.")
        ttk.Label(self, textvariable=self.status, wraplength=1250).pack(fill="x", pady=10)
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)
        self.pages = {}
        for title in ("Overview", "Requirements", "Not mentioned", "Documents", "Framework relationships", "Reports", "History", "Framework updates", "Settings"):
            frame = ttk.Frame(self.tabs, padding=10)
            self.tabs.add(frame, text=title)
            self.pages[title] = frame
        self.overview = ScrolledText(self.pages["Overview"], wrap="word", height=18)
        self.overview.pack(fill="both", expand=True)
        self.chart = tk.Canvas(self.pages["Overview"], height=100, highlightthickness=0)
        self.chart.pack(fill="x")
        self.framework_totals = self.tree(self.pages['Overview'], ('Framework', 'Requirements', *alignment.STATUSES))
        self.framework_totals.configure(height=4)
        filters = ttk.Frame(self.pages["Requirements"])
        filters.pack(fill="x")
        ttk.Label(filters, text="Search requirements").pack(side="left")
        self.search = tk.StringVar()
        ttk.Entry(filters, textvariable=self.search).pack(side="left", fill="x", expand=True, padx=8)
        self.filter = tk.StringVar(value="All")
        ttk.Combobox(filters, textvariable=self.filter, state="readonly", values=("All", *alignment.STATUSES), width=22).pack(side="left")
        self.search.trace_add("write", lambda *_: self.filter_rows())
        self.filter.trace_add("write", lambda *_: self.filter_rows())
        panes = ttk.Panedwindow(self.pages["Requirements"], orient="horizontal")
        panes.pack(fill="both", expand=True, pady=(10, 0))
        left, right = ttk.Frame(panes), ttk.Frame(panes)
        panes.add(left, weight=2)
        panes.add(right, weight=3)
        self.requirements = self.tree(left, ("Reference", "Alignment", "Passages"))
        self.requirements.configure(show='tree headings')
        self.requirements.heading('#0', text='Framework / section')
        self.requirements.column('#0', width=180, minwidth=100)
        self.requirements.bind("<<TreeviewSelect>>", self.select_requirement)
        self.detail = ScrolledText(right, wrap="word", height=12)
        self.detail.pack(fill="both", expand=True)
        ttk.Label(right, text="Matching policy passages — select to see the original text").pack(anchor="w", pady=4)
        self.evidence = ttk.Combobox(right, state="readonly")
        self.evidence.pack(fill="x")
        self.evidence.bind("<<ComboboxSelected>>", self.show_evidence)
        self.passage = ScrolledText(right, wrap="word", height=9)
        self.passage.pack(fill="both", expand=True)
        self.passage.tag_configure("match", background="#ffe394", foreground="#182229")
        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=6)
        ttk.Button(actions, text="Related frameworks", command=self.relationships).pack(side="left", padx=8)
        self.gaps = self.tree(self.pages["Not mentioned"], ("Reference", "Framework requirement", "Status"))
        self.gaps.bind("<<TreeviewSelect>>", self.open_gap)
        self.doc_tree = self.tree(self.pages["Documents"], ("File", "Read status", "Source", "Retained / extracted passages"))
        self.doc_tree.bind("<<TreeviewSelect>>", self.show_document)
        self.doc_text = ScrolledText(self.pages["Documents"], height=14, wrap="word")
        self.doc_text.pack(fill="both", expand=True)
        ttk.Button(self.pages["Documents"], text="Open original after hash check", command=self.open_original).pack(anchor="w")
        self.graph = tk.Canvas(self.pages["Framework relationships"], height=180, background="white")
        self.graph.pack(fill="x")
        self.edges = self.tree(self.pages["Framework relationships"], ("Source", "Relationship", "Target", "Evidence relation"))
        self.graph_status = tk.StringVar(value="Choose a requirement to see its bounded neighbourhood.")
        ttk.Label(self.pages["Framework relationships"], textvariable=self.graph_status).pack(anchor="w")
        ttk.Label(self.pages["Reports"], text="Export framework alignment and requirements not mentioned as HTML, CSV, Markdown or JSON.\nChoose which frameworks and whether to include the matching policy passages.", wraplength=900).pack(anchor="w", pady=10)
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
        self.set_text(self.settings, "Engine " + ENGINE_VERSION + "\n\nNo listener, telemetry or AI inference. Framework downloads occur only through the explicit update action.\n\nComparisons retain extracted text so you can inspect the matching passages. Original files are not embedded.\n\nAssessment files are ordinary, unencrypted SQLite databases. Store them in an approved local folder.\n\nCorpus: " + json.dumps(installed, ensure_ascii=False, indent=2))
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
        dialog.title("Select documents and frameworks")
        dialog.geometry("780x750")
        form = ttk.Frame(dialog, padding=18)
        form.pack(fill="both", expand=True)
        values = {}
        defaults = dict(Name="Framework alignment", Organisation="", Scope="")
        if self.state and destination:
            defaults.update(Name=self.state["run"]["name"], Organisation=self.state["run"].get("organisation", ""), Scope=self.state["run"]["scope"]["description"])
        for label, default in defaults.items():
            ttk.Label(form, text=label).pack(anchor="w", pady=(8, 0))
            values[label] = tk.StringVar(value=default)
            ttk.Entry(form, textvariable=values[label]).pack(fill="x")
        ttk.Label(form, text='Compare against — select one or more frameworks', wraplength=700).pack(anchor='w', pady=10)
        previous = {f['id'] for f in self.state['run']['versions']['frameworks']} if self.state and destination else {next(iter(choices))}
        selected_frameworks = {key: tk.BooleanVar(value=key in previous and key in choices) for key in corpus.REVIEW_FRAMEWORKS}
        for key, variable in selected_frameworks.items():
            label = corpus.REVIEW_FRAMEWORKS[key]
            label += ' — ' + choices[key]['edition'] if key in choices else ' — local source unavailable'
            ttk.Checkbutton(form, text=label, variable=variable, state='normal' if key in choices else 'disabled').pack(anchor='w')
        selected = tk.Listbox(form, height=5, selectmode="extended")
        selected.pack(fill="both", expand=True, pady=8)
        def add():
            for path in filedialog.askopenfilenames(parent=dialog, filetypes=[("Documents and ZIP archives", "*.pdf *.docx *.txt *.md *.zip")]):
                if path not in selected.get(0, "end"):
                    selected.insert("end", path)
        def remove():
            for index in reversed(selected.curselection()):
                selected.delete(index)
        buttons = ttk.Frame(form)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Add files or ZIP archives", command=add).pack(side="left")
        ttk.Button(buttons, text="Exclude selected", command=remove).pack(side="left", padx=8)
        ttk.Label(form, text="Select several files at once, add files in batches, or choose a ZIP. Supported documents: PDF, DOCX, TXT and Markdown.", wraplength=700).pack(anchor="w", pady=8)
        def run():
            frameworks = [key for key, variable in selected_frameworks.items() if variable.get()]
            if not frameworks:
                messagebox.showerror('Choose a framework', 'Select at least one framework to compare against.', parent=dialog)
                return
            if not values["Scope"].get().strip() or not selected.size():
                messagebox.showerror("Scope required", "Describe the scope and select at least one document.", parent=dialog)
                return
            path = destination or filedialog.asksaveasfilename(parent=dialog, defaultextension=".wacc", filetypes=[("WACC assessment", "*.wacc")])
            if not path:
                return
            options = dict(paths=list(selected.get(0, "end")), name=values["Name"].get(), scope=values["Scope"].get(),
                           organisation=values["Organisation"].get(), retention="extracted",
                           framework=frameworks[0], also=frameworks[1:])
            dialog.destroy()
            self.start_analysis(path, options)
        ttk.Button(form, text="Compare and save", command=run).pack(anchor="e", pady=10)

    def start_analysis(self, path, options):
        self.busy = True
        self.cancel.clear()
        self.status.set("Reading documents and matching passages to the selected frameworks…")
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
        run = self.state['run']
        self.aligned = alignment.for_run(run)
        self.rows_by_id = {r['id']: r for r in run['requirements']}
        self.search_text = {r['id']: (r['id'] + ' ' + r['heading'] + ' ' + r['authoritativeText']).casefold()
                            for r in run['requirements']}
        totals = alignment.summary(run['requirements'], self.aligned)
        self.status.set(run['name'] + ' | ' + run['scope']['description'])
        overview = [run['name'], 'Scope: ' + run['scope']['description'], '', alignment.DESCRIPTION, '',
                    'Mentioned: clear shared wording about the requirement.',
                    'Related wording: a possible topic match, reference or qualified statement.',
                    'Not mentioned: no matching passage was found in the supplied documents.',
                    'Unable to check: some document text could not be read or was not retained.', '',
                    '%d documents; %d requirements across %d frameworks' %
                    (len(run['documents']), totals['requirements'], len(run['versions']['frameworks']))]
        overview += [status + ': ' + str(count) for status, count in totals['counts'].items()]
        if run['scope'].get('skippedInputs'):
            overview.append('Unsupported files skipped: ' + str(len(run['scope']['skippedInputs'])))
        overview += ['', 'Select a requirement to see its matching policy passages. Use Not mentioned to identify topics to add.',
                     '', 'Comparison method: ' + run['versions'].get('alignment', alignment.VERSION), 'Run: ' + run['runId']]
        self.set_text(self.overview, '\n'.join(overview))
        self.framework_totals.delete(*self.framework_totals.get_children())
        for f in alignment.framework_summaries(run, self.aligned):
            self.framework_totals.insert('', 'end', values=(corpus.REVIEW_FRAMEWORKS.get(f['id'], f['title']),
                f['requirements'], *(f['counts'][status] for status in alignment.STATUSES)))
        self.chart.delete('all')
        start, width = 10, max(850, self.chart.winfo_width()-20)
        for index, (status, count) in enumerate(totals['counts'].items()):
            end = start + width * count / max(1, totals['requirements'])
            self.chart.create_rectangle(start, 8, end, 34, fill=('#266b47', '#b38519', '#94665c', '#8b939c')[index], outline='white')
            self.chart.create_text(10 + index*230, 60, text=status + ': ' + str(count), anchor='w', fill='black')
            start = end
        self.filter_rows()
        self.gaps.delete(*self.gaps.get_children())
        for row in run['requirements']:
            status = self.aligned[row['id']]['status']
            if status in ('Not mentioned', 'Unable to check'):
                self.gaps.insert('', 'end', iid=row['id'], values=(row['id'], row['authoritativeText'], status))
        self.doc_tree.delete(*self.doc_tree.get_children())
        for doc in run['documents']:
            self.doc_tree.insert('', 'end', iid=doc['id'], values=(doc['name'], doc['status'],
                'ZIP archive' if doc.get('archiveMember') else 'File',
                '%d / %d' % (len(doc['passages']), doc.get('extractedPassageCount', len(doc['passages'])))))
        self.set_text(self.doc_text, 'Select a document to inspect its text.' +
                      ('\n\nFiles skipped (unsupported format):\n' + '\n'.join(run['scope']['skippedInputs']) if run['scope'].get('skippedInputs') else ''))
        self.history.delete(*self.history.get_children())
        for history in self.state['history']:
            self.history.insert('', 'end', iid=history['id'], values=(history['id'], history['createdAt']))
        self.set_text(self.history_text, json.dumps(run['versions'], ensure_ascii=False, indent=2))

    def filter_rows(self):
        if not self.state:
            return
        self.requirements.delete(*self.requirements.get_children())
        query, status = self.search.get().casefold(), self.filter.get()
        for row in self.rows_by_id.values():
            result = self.aligned[row['id']]
            if query not in self.search_text[row['id']] or status != 'All' and status != result['status']:
                continue
            group = 'group/' + row['frameworkId'] + '/' + str(row['parentId'])
            if not self.requirements.exists(group):
                self.requirements.insert('', 'end', iid=group, text=row['frameworkId'] + ' / ' + str(row['parentId']) + ' ' + row['heading'], open=True)
            self.requirements.insert(group, 'end', iid=row['id'], values=(row['officialReference'], result['status'], result['matchCount']))

    def current(self):
        selected = self.requirements.selection()
        return self.rows_by_id.get(selected[0]) if self.state and selected else None

    def select_requirement(self, _=None):
        row = self.current()
        if not row:
            return
        result = self.aligned[row['id']]
        self.set_text(self.detail, row['id'] + ' — ' + row['heading'] + '\n\n' + row['context'] + '\n' + row['authoritativeText'] +
                      '\n\n' + result['status'] + ' · ' + str(result['matchCount']) + ' matching passages')
        self.evidence.configure(values=[reports.location(match) for match in result['matches']])
        self.evidence.set('')
        self.set_text(self.passage, 'No matching passage found.' if not result['matches'] else 'Select a matching passage above.')
        if result['matches']:
            self.evidence.current(0)
            self.show_evidence()

    def show_evidence(self, _=None):
        row = self.current()
        index = self.evidence.current()
        if not row or index < 0:
            return
        match = self.aligned[row['id']]['matches'][index]
        self.set_text(self.passage, match['excerpt'] + '\n\n' + reports.location(match) + '\n' + '\n'.join(match['cautions']))
        self.passage.tag_remove('match', '1.0', 'end')
        for span in match['matchedSpans']:
            self.passage.tag_add('match', '1.0 + %d chars' % span['start'], '1.0 + %d chars' % span['end'])

    def open_gap(self, _=None):
        selection = self.gaps.selection()
        if selection:
            self.search.set("")
            self.filter.set("All")
            self.requirements.selection_set(selection[0])
            self.requirements.see(selection[0])
            self.tabs.select(self.pages["Requirements"])

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
        doc = next(d for d in self.state["run"]["documents"] if d["id"] == ids[0])
        self.guarded(lambda: os.startfile(str(store.verified_source(doc))))

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
        ttk.Checkbutton(box, text='Include matching policy passages', variable=full).pack(anchor='w', pady=12)
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
