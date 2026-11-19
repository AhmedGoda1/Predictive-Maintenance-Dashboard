// CA_Screen - which screen the application is on: phone (up to 600px), tablet (601 to 1024px) or
// desktop (1025px and up), the same three names the view's screen= attribute uses. It has no visible
// part. It marks the view's body with data-screen="phone|tablet|desktop" so CSS can react, answers
// getValue() with the current name (a process reads {#App#screen.getValue()}), and fires a "Screen"
// event whenever the window crosses a breakpoint, with the name as the property screen
// ({#App#screen%screen} in the process).
//
// External component (ES module, export class): declared in the manifest as
//   <component name="Screen" tag="screen" class="CA_Screen" href="ui/DesignKit/CA_Screen.js" container="false">
//     <skin href="ui/DesignKit/screen.xsl"/>
//   </component>
// Component, sys and CloneObject are the runtime's globals in the window that imports this module.
// ASCII only: a webshare labels .js files ISO-8859-1.

export class CA_Screen extends Component {
  constructor() {
    super();
    this.onChange = this.onChange.bind(this);
    this.queries = [];
    this.current = '';
  }

  init() {
    this.dom = this.getElement();
    const win = (this.doc && this.doc.defaultView) || window;
    this.queries = [
      ['phone', win.matchMedia('(max-width: 600px)')],
      ['tablet', win.matchMedia('(min-width: 601px) and (max-width: 1024px)')]
    ];
    this.queries.forEach(([, q]) => {
      if (q.addEventListener) q.addEventListener('change', this.onChange); else q.addListener(this.onChange);
    });
    this.current = this.measure();
    this.mark();
  }

  measure() {
    for (const [name, q] of this.queries) if (q.matches) return name;
    return 'desktop';
  }

  mark() {
    if (this.doc && this.doc.body) this.doc.body.setAttribute('data-screen', this.current);
    if (this.dom) this.dom.setAttribute('data-screen', this.current);
  }

  getValue() { return this.current || ''; }
  setValue() { /* read-only: the window decides */ }

  onChange(winEvt) {
    const next = this.measure();
    if (next === this.current) return;
    this.current = next;
    this.mark();
    this.setProperty('screen', next, null, true);
    sys.evtMng.notifyListeners(this, 'Screen', CloneObject(winEvt || {}, { screen: next }), null);
  }
}
