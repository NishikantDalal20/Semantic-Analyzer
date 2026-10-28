from flask import Flask, render_template, request, jsonify
import re
app = Flask(__name__)

TOKEN_RE = re.compile(r'(?P<SPACE>\s+)|(?P<COMMENT>//[^\n]*|/\*[\s\S]*?\*/)|(?P<NUMBER>\d+(?:\.\d+)?)|(?P<STRING>"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')|(?P<IDENT>[A-Za-z_]\w*)|(?P<OP>==|!=|<=|>=|&&|\|\||[+\-*/%=<>!])|(?P<PUNCT>[{}();,])|(?P<OTHER>.)')
KEYWORDS={'int','float','bool','string','if','else','while','true','false'}

def lex(source):
    out=[]; errors=[]; line=col=1
    for m in TOKEN_RE.finditer(source):
        value=m.group(); kind=m.lastgroup; start=(line,col)
        if kind not in ('SPACE','COMMENT'):
            if kind=='OTHER': errors.append(diag('Lexical',f'Unexpected character {value!r}.',*start))
            else:
                if kind=='IDENT' and value in KEYWORDS: kind='KEYWORD'
                out.append({'kind':kind,'value':value,'line':line,'column':col})
        n=value.count('\n')
        if n: line+=n; col=len(value.rsplit('\n',1)[-1])+1
        else: col+=len(value)
    out.append({'kind':'EOF','value':'','line':line,'column':col})
    return out,errors

def diag(phase,message,line=1,column=1,severity='error',suggestion=None):
    d={'phase':phase,'message':message,'line':line,'column':column,'severity':severity}
    if suggestion: d['suggestion']=suggestion
    return d

class ParseError(Exception):
    def __init__(self,message,t): self.message=message; self.t=t
class Parser:
    prec={'||':1,'&&':2,'==':3,'!=':3,'<':4,'>':4,'<=':4,'>=':4,'+':5,'-':5,'*':6,'/':6,'%':6}
    def __init__(self,tokens): self.ts=tokens; self.i=0
    def cur(self): return self.ts[min(self.i,len(self.ts)-1)]
    def check(self,v=None,k=None): return (v is None or self.cur()['value']==v) and (k is None or self.cur()['kind']==k)
    def take(self): t=self.cur(); self.i+=self.cur()['kind']!='EOF'; return t
    def expect(self,v=None,k=None):
        if self.check(v,k): return self.take()
        t=self.cur(); want=repr(v) if v else k or 'token'; raise ParseError(f'Expected {want}, found {t["value"]!r}.',t)
    def parse(self):
        body=[]
        while not self.check(k='EOF'): body.append(self.stmt())
        return {'type':'Program','body':body}
    def stmt(self):
        if self.check('{'):
            tok=self.take(); body=[]
            while not self.check('}') and not self.check(k='EOF'): body.append(self.stmt())
            self.expect('}'); return {'type':'Block','body':body,'token':tok}
        if self.check(';'): self.take(); return {'type':'Empty'}
        if self.check(k='KEYWORD') and self.cur()['value'] in ('int','float','bool','string'):
            typ=self.take(); name=self.expect(k='IDENT'); val=None
            if self.check('='): self.take(); val=self.expr()
            self.expect(';'); return {'type':'Declaration','var_type':typ['value'],'name':name['value'],'token':name,'value':val}
        if self.check(k='KEYWORD') and self.cur()['value'] in ('if','while'):
            kw=self.take(); self.expect('('); cond=self.expr(); self.expect(')'); body=self.stmt()
            node={'type':kw['value'].capitalize(),'condition':cond,'body':body,'token':kw}
            if kw['value']=='if' and self.check('else'): self.take(); node['else_body']=self.stmt()
            return node
        if self.check(k='IDENT'):
            name=self.take(); self.expect('='); val=self.expr(); self.expect(';')
            return {'type':'Assign','name':name['value'],'token':name,'value':val}
        raise ParseError(f'Unexpected token {self.cur()["value"]!r}; expected declaration, assignment or block.',self.cur())
    def expr(self,minp=1):
        t=self.cur()
        if self.check('!') or self.check('-') or self.check('+'):
            op=self.take(); left={'type':'Unary','op':op['value'],'value':self.expr(7),'token':op}
        elif self.check('('): self.take(); left=self.expr(); self.expect(')')
        elif t['kind']=='NUMBER':
            self.take(); left={'type':'Literal','value':t['value'],'literal_type':'float' if '.' in t['value'] else 'int','token':t}
        elif t['kind']=='STRING': self.take(); left={'type':'Literal','value':t['value'],'literal_type':'string','token':t}
        elif t['value'] in ('true','false'): self.take(); left={'type':'Literal','value':t['value'],'literal_type':'bool','token':t}
        elif t['kind']=='IDENT': self.take(); left={'type':'Identifier','name':t['value'],'token':t}
        else: raise ParseError(f'Expected expression, found {t["value"]!r}.',t)
        while self.cur()['value'] in self.prec and self.prec[self.cur()['value']]>=minp:
            op=self.take(); right=self.expr(self.prec[op['value']]+1)
            left={'type':'Binary','op':op['value'],'left':left,'right':right,'token':op}
        return left

def loc(tok): return (tok or {}).get('line',1),(tok or {}).get('column',1)
def analyze(ast):
    errors=[]; warnings=[]; scopes=[{'id':0,'name':'Global','parent':None,'variables':[]}]; env=[{}]; nextid=[1]; symbols=[]
    def issue(msg,t,severity='error',suggestion=None):
        line,col=loc(t); d=diag('Semantic',msg,line,col,severity,suggestion); (warnings if severity=='warning' else errors).append(d)
    def lookup(name):
        for scope in reversed(env):
            if name in scope:return scope[name]
        return None
    def infer(n):
        typ=n['type']; tok=n.get('token')
        if typ=='Literal': return n['literal_type']
        if typ=='Identifier':
            v=lookup(n['name'])
            if not v: issue(f"Variable '{n['name']}' is not declared in this scope.",tok,suggestion=f"Declare '{n['name']}' before using it."); return 'unknown'
            if not v['initialized']: issue(f"Variable '{n['name']}' may be used before initialization.",tok,'warning')
            return v['type']
        if typ=='Unary':
            a=infer(n['value']); op=n['op']
            if op=='!' and a not in ('bool','unknown'): issue("Operator '!' requires a bool operand.",tok); return 'unknown'
            if op in ('+','-') and a not in ('int','float','unknown'): issue(f"Unary '{op}' requires a numeric operand.",tok); return 'unknown'
            return 'bool' if op=='!' else a
        if typ=='Binary':
            a=infer(n['left']); b=infer(n['right']); op=n['op']
            if 'unknown' in (a,b): return 'unknown'
            if op in ('+','-','*','/','%'):
                if a not in ('int','float') or b not in ('int','float'): issue(f"Operator '{op}' requires numeric operands; received {a} and {b}.",tok); return 'unknown'
                return 'float' if op=='/' or 'float' in (a,b) else 'int'
            if op in ('<','>','<=','>='):
                if a not in ('int','float') or b not in ('int','float'): issue(f"Comparison '{op}' requires numeric operands.",tok)
                return 'bool'
            if op in ('==','!='):
                if a!=b and not {a,b}<={'int','float'}: issue(f"Cannot compare {a} and {b} with '{op}'.",tok)
                return 'bool'
            if op in ('&&','||'):
                if a!='bool' or b!='bool': issue(f"Operator '{op}' requires bool operands.",tok)
                return 'bool'
        return 'unknown'
    def walk(n,sid=0):
        kind=n['type']
        if kind=='Program':
            for x in n['body']: walk(x,0)
        elif kind=='Block':
            new=nextid[0]; nextid[0]+=1; name=f'Block {new}'; scopes.append({'id':new,'name':name,'parent':sid,'variables':[]}); env.append({})
            for x in n['body']: walk(x,new)
            env.pop()
        elif kind=='Declaration':
            name=n['name']; t=n['var_type']; tok=n['token']
            if name in env[-1]: issue(f"Variable '{name}' is already declared in this scope.",tok,suggestion='Use another name or remove the duplicate declaration.'); return
            valtype=infer(n['value']) if n.get('value') else None
            if valtype and valtype!='unknown' and not (t==valtype or (t=='float' and valtype=='int')): issue(f"Cannot initialize {t} variable '{name}' with {valtype} value.",tok,suggestion=f'Use a {t} expression or change the declared type.')
            item={'name':name,'type':t,'scope':scopes[sid]['name'],'scope_id':sid,'line':tok['line'],'column':tok['column'],'initialized':bool(n.get('value')),'status':'Initialized' if n.get('value') else 'Declared'}
            env[-1][name]=item; scopes[sid]['variables'].append(item); symbols.append(item)
        elif kind=='Assign':
            valtype=infer(n['value']); found=lookup(n['name'])
            if not found: issue(f"Variable '{n['name']}' is not declared in this scope.",n['token'],suggestion=f"Declare '{n['name']}' before assigning to it.")
            else:
                if valtype!='unknown' and not (found['type']==valtype or (found['type']=='float' and valtype=='int')): issue(f"Cannot assign {valtype} value to {found['type']} variable '{n['name']}'.",n['token'],suggestion=f"Convert the value to {found['type']} or change the variable type.")
                found['initialized']=True; found['status']='Initialized'
        elif kind in ('If','While'):
            ct=infer(n['condition'])
            if ct not in ('bool','unknown'): issue(f"{kind.lower()} condition must be bool, but received {ct}.",n.get('token'))
            walk(n['body'],sid)
            if n.get('else_body'): walk(n['else_body'],sid)
    walk(ast)
    return errors,warnings,symbols,scopes

def json_ast(node):
    if isinstance(node,list): return [json_ast(x) for x in node]
    if not isinstance(node,dict): return node
    out={}
    for k,v in node.items():
        if k=='token': out['location']={'line':v['line'],'column':v['column']}
        elif isinstance(v,(dict,list)): out[k]=json_ast(v)
        else: out[k]=v
    return out

def fold(n):
    if isinstance(n,list): return [fold(x) for x in n]
    if not isinstance(n,dict): return n
    n={k:fold(v) if isinstance(v,(dict,list)) else v for k,v in n.items()}
    if n.get('type')=='Binary' and n.get('left',{}).get('type')=='Literal' and n.get('right',{}).get('type')=='Literal':
        a=n['left']; b=n['right']; op=n['op']
        if a.get('literal_type') in ('int','float') and b.get('literal_type') in ('int','float'):
            try:
                x=float(a['value']); y=float(b['value']); val={'+':lambda:x+y,'-':lambda:x-y,'*':lambda:x*y,'/':lambda:x/y,'%':lambda:x%y}.get(op)
                if val:
                    z=val(); integer=a['literal_type']==b['literal_type']=='int' and op!='/'
                    return {'type':'Literal','value':str(int(z)) if integer and z.is_integer() else str(z),'literal_type':'int' if integer else 'float','token':n.get('token')}
            except (ZeroDivisionError,ValueError,TypeError): pass
    return n

def tac(ast):
    code=[]; count=[0]
    def expr(n):
        if n['type']=='Literal': return n['value']
        if n['type']=='Identifier': return n['name']
        if n['type']=='Unary':
            v=expr(n['value']); count[0]+=1; t=f't{count[0]}'; code.append(f'{t} = {n["op"]}{v}'); return t
        if n['type']=='Binary':
            a=expr(n['left']); b=expr(n['right']); count[0]+=1; t=f't{count[0]}'; code.append(f'{t} = {a} {n["op"]} {b}'); return t
        return '?'
    def stmt(n):
        if n['type']=='Program' or n['type']=='Block':
            for x in n['body']: stmt(x)
        elif n['type']=='Declaration' and n.get('value'): code.append(f'{n["name"]} = {expr(n["value"])}')
        elif n['type']=='Assign': code.append(f'{n["name"]} = {expr(n["value"])}')
        elif n['type'] in ('If','While'):
            code.append(f'# {n["type"].lower()} condition: {expr(n["condition"])}'); stmt(n['body'])
            if n.get('else_body'): code.append('# else'); stmt(n['else_body'])
    stmt(ast); return code

def compile_source(source):
    tokens,lex_errors=lex(source); shown=[t for t in tokens if t['kind']!='EOF']
    empty={'symbols':[],'scopes':[{'id':0,'name':'Global','parent':None,'variables':[]}],'warnings':[],'ast':None,'tac':[],'optimized_tac':[]}
    if lex_errors: return {'ok':False,'tokens':shown,'errors':lex_errors,'message':'Fix lexical errors before continuing.',**empty}
    try: ast=Parser(tokens).parse()
    except ParseError as e:
        line,col=loc(e.t); return {'ok':False,'tokens':shown,'errors':[diag('Syntax',e.message,line,col)],'message':'Fix syntax errors before semantic analysis.',**empty}
    errors,warnings,symbols,scopes=analyze(ast); optimized=fold(ast)
    return {'ok':not errors,'tokens':shown,'errors':errors,'warnings':warnings,'symbols':symbols,'scopes':scopes,'ast':json_ast(ast),'tac':tac(ast),'optimized_tac':tac(optimized),'message':'Analysis completed successfully.' if not errors else 'Analysis completed with semantic errors.'}

@app.route('/')
def index(): return render_template('index.html')
@app.route('/analyze',methods=['POST'])
def analyze_route():
    data=request.get_json(silent=True) or {}; source=data.get('code','')
    if not isinstance(source,str): return jsonify({'error':'Code must be text.'}),400
    return jsonify(compile_source(source))
if __name__=='__main__': app.run(debug=True)
