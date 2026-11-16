"""Reviewed original AP Biology Unit 3 guide content and source-only fallback."""
from __future__ import annotations
import re

SECTIONS = [
    ("3.1 Enzymes",
     ["Enzymes lower activation energy, speeding reactions without changing overall ΔG or equilibrium.",
      "The active site's shape and chemical properties influence substrate binding and catalytic specificity.",
      "At a fixed enzyme concentration, reaction rate can plateau when active sites become saturated."],
     ["Even an exergonic reaction may proceed slowly because reactants must cross an activation-energy barrier. Catalysts lower that barrier but do not add energy to reactants.",
      "Binding is influenced by molecular interactions and can involve induced fit. Mutations affecting active-site shape or charge may change substrate binding or catalytic activity.",
      "Increasing substrate concentration raises initial rate only until most active sites are occupied. Extra active enzyme can raise maximum rate if enough substrate is present."],
     "Why will doubling substrate concentration not necessarily double the enzyme's rate?",
     "An enzyme does not change the overall free-energy change of a reaction."),
    ("3.2 Environmental Impacts on Enzyme Function",
     ["Temperature and pH can affect enzyme structure, binding, and reaction rate.",
      "Excessive heat or extreme pH can disrupt protein structure and reduce function.",
      "Competitive inhibitors compete at the active site; noncompetitive inhibitors bind elsewhere and reduce activity.",
      "Enzyme experiments should change one independent variable and measure reaction rate."],
     ["Temperature can initially increase collision frequency, but too much heat can destabilize interactions important to protein folding.",
      "Changing pH alters charge on some amino-acid side chains, potentially changing enzyme folding or substrate interactions.",
      "Competitive inhibition may be reduced by increasing substrate concentration. Noncompetitive inhibition may persist despite more substrate.",
      "In an enzyme-pH lab, pH is the independent variable and reaction rate is the dependent variable. Keep temperature, enzyme concentration, substrate concentration, and measurement time consistent."],
     "An enzyme's highest measured rate is at pH 6 among three tested values. What is supported, and what is not?",
     "The highest measured point is not necessarily the exact global optimum."),
    ("3.3 Cellular Energy",
     ["Exergonic processes have negative ΔG and release free energy; endergonic processes have positive ΔG and require free-energy input.",
      "ATP hydrolysis can be coupled to endergonic cellular processes.",
      "Oxidation is electron loss and reduction is electron gain.",
      "Electron carriers such as NADH and NADPH transfer reducing power between reactions."],
     ["ΔG describes thermodynamic favorability, not speed. A favorable reaction can still be slow if the activation-energy barrier is high.",
      "Cells couple ATP hydrolysis to processes including active transport and biosynthesis, so the overall coupled process can be favorable.",
      "NADH commonly carries electrons toward respiratory electron transport. NADPH supplies electrons used by the Calvin cycle and other biosynthetic pathways."],
     "What is the difference between ΔG and activation energy?",
     "A negative ΔG does not mean a reaction happens quickly."),
    ("3.4 Photosynthesis",
     ["Light reactions take place at thylakoid membranes; the Calvin cycle occurs in the stroma.",
      "Chlorophyll absorbs light energy; water supplies electrons and is the source of released O₂.",
      "Electron transport builds a thylakoid proton gradient that powers ATP synthase.",
      "The Calvin cycle uses ATP and NADPH to fix CO₂ into organic molecules, yielding G3P while regenerating RuBP."],
     ["Thylakoid membranes separate the thylakoid lumen from the surrounding stroma and contain the photosystems and transport proteins.",
      "Light energizes electrons in photosystem II. Water replaces electrons lost from PSII and releases O₂. Electrons pass through transport proteins, are re-energized at photosystem I, and help reduce NADP+ to NADPH.",
      "H+ accumulates in the lumen and flows through ATP synthase into the stroma, powering ATP production. ATP and NADPH support carbon fixation by the Calvin cycle.",
      "In leaf-disk flotation experiments, ET50 is the time until half the disks float. Under controlled conditions a shorter ET50 usually indicates more rapid net oxygen accumulation."],
     "What happens to ATP production if a chemical collapses the thylakoid H+ gradient?",
     "The O₂ released by photosynthesis comes from H₂O, not from CO₂."),
    ("3.5 Cellular Respiration",
     ["Glycolysis occurs in the cytosol and yields two pyruvate, net two ATP, and two NADH per glucose.",
      "In eukaryotes, pyruvate oxidation and the citric acid cycle occur in the mitochondrial matrix, releasing CO₂ and producing reduced electron carriers.",
      "The electron transport chain is in the inner mitochondrial membrane, and O₂ is the final electron acceptor.",
      "Electron transport builds an H+ gradient powering ATP synthase; fermentation regenerates NAD+ so glycolysis can continue."],
     ["Glycolysis breaks glucose into two three-carbon pyruvate molecules and generates ATP directly without requiring O₂ for that step.",
      "Reduced electron carriers from earlier steps deliver electrons to the inner-membrane electron transport chain. Electron flow drives H+ pumping from the matrix toward the intermembrane space.",
      "H+ returns through ATP synthase, producing ATP. Oxygen accepts electrons at the end and allows the chain to keep operating.",
      "Without adequate oxygen, fermentation transfers electrons from NADH to organic molecules, regenerating NAD+ and allowing glycolysis to continue at a much smaller net ATP yield."],
     "Predict the effect on ATP production if the mitochondrial inner membrane becomes leaky to H+.",
     "Fermentation's essential role is NAD+ regeneration; most aerobic ATP comes from oxidative phosphorylation.")
]

COMPARISONS = [
    ("Activation energy vs. ΔG","Activation energy governs reaction rate; ΔG is the overall free-energy change."),
    ("Competitive vs. noncompetitive inhibition","Competitive inhibitors bind the active site, while noncompetitive inhibitors bind elsewhere."),
    ("Thylakoid membranes vs. stroma","Light reactions occur at the thylakoid membranes; the Calvin cycle occurs in the stroma."),
    ("Glycolysis vs. oxidative phosphorylation","Glycolysis makes net two ATP per glucose in the cytosol; oxidative phosphorylation uses the mitochondrial proton gradient."),
    ("Photosynthesis vs. respiration","Photosynthesis captures light and fixes carbon, whereas respiration extracts chemical energy from organic molecules. They are not simple reverses.")
]

OBJECTIVE = re.compile(r'(?i)^(?:\d+(?:\.\d+){0,3}\s*)?(?:i can\s+|students?\s+(?:should|will)\s+(?:be able to\s+)?)?(explain|describe|identify|compare|predict|analy[sz]e|interpret|evaluate|calculate|determine|justify|construct|design|model|discuss)\b')
def clean_line(value):
    return re.sub(r'\s+',' ',str(value or '')).strip()[:200]

def extract_objectives(rows):
    result,seen=[],set()
    for row in rows:
        for raw in str(row.get('text') or '').splitlines():
            line=re.sub(r'^[\s•*-]+','',raw).strip()
            if 24<=len(line)<=200 and OBJECTIVE.match(line) and line.lower() not in seen:
                seen.add(line.lower())
                result.append((clean_line(line),clean_line(row.get('filename'))))
                if len(result)>=22:return result
    return result

def unit3_guide(mode,rows):
    if mode not in ('concise','detailed','exam'):raise ValueError('Invalid study guide style.')
    title={'concise':'Unit 3 Quick Review','detailed':'Unit 3 Detailed Study Guide','exam':'Unit 3 Test Review'}[mode]
    parts=['# AP Biology — '+title,'',
           '**Source note:** This is original supplemental AP Biology Unit 3 content. It is NOT a set of answers extracted from your uploaded objectives or official exam questions.','']
    if rows:parts+=['**Uploaded files:** '+', '.join(clean_line(row.get('filename')) for row in rows),'']
    goals=extract_objectives(rows)
    if goals:
        parts+=['## Objectives found in your files','']
        parts+=['- '+text+' (Source: '+source+')' for text,source in goals]
        parts+=['','The explanations below are supplemental; check your teacher-specific learning targets.','']
    parts+=['## Key concepts','']
    for heading,main_points,explanations,checkpoint,misconception in SECTIONS:
        parts+=['### '+heading,'']
        parts+=['- '+statement for statement in main_points]
        parts.append('')
        if mode in ('detailed','exam'):
            parts+=['**How and why it works**','']
            for explanation in explanations:parts+=[explanation,'']
        parts+=['**Check your understanding:** '+checkpoint,'']
        if mode=='exam':parts+=['**Common mistake:** '+misconception,'']
    if mode in ('detailed','exam'):
        parts+=['## High-yield comparisons','']
        parts+=['- **'+name+':** '+meaning for name,meaning in COMPARISONS]
        parts+=['','## Data analysis and experiment design','',
                '- Identify the independent variable, dependent variable, and controls.',
                '- Calculate a reaction rate from change in measured value divided by elapsed time; include units.',
                '- Use numerical evidence to justify trends without overclaiming an exact optimum.',
                '- Compare ET50 results only when the light conditions and other factors are controlled.','']
    if mode=='exam':
        parts+=['## Written-response practice','',
                '1. Compare enzyme reaction rates across five pH values. Identify variables, cite the measured trend, and explain how pH could alter enzyme function.',
                '2. Predict what happens to photosynthetic ATP synthesis and carbon fixation if the thylakoid proton gradient is lost.',
                '3. Explain how blocking mitochondrial electron transport affects ATP production and the need to regenerate NAD+.','',
                'Answer with a claim, a biological mechanism, and relevant evidence where available.','']
    parts+=['---','','**Reminder:** Compare supplemental explanations with your teacher’s notes and objectives.']
    return title,'\n'.join(parts)

def source_guide(mode,rows,facts):
    title={'concise':'Source Quick Review','detailed':'Source Study Guide','exam':'Source Test Checklist'}[mode]
    parts=['# AP Biology — '+title,'',
        '**Source note:** This guide only organizes explicit information in your selected files. It cannot supply answers to objectives that contain no explanations.','',
        '## Selected files','']
    parts+=['- '+clean_line(row['filename']) for row in rows]
    parts.append('')
    if facts:
        parts+=['## Explicit concepts from your notes','']
        for fact in facts[:60 if mode=='detailed' else 25]:
            parts+=['**'+clean_line(fact['term'])+'** — '+clean_line(fact['definition'])+' (Source: '+clean_line(fact['source_name'])+')','']
    goals=extract_objectives(rows)
    if goals:
        parts+=['## Learning objectives to review','']
        parts+=['- [ ] '+objective+' (Source: '+source+')' for objective,source in goals]
        parts+=['','**Objectives are goals, not explanations. Upload substantive lesson notes for factual answers.**','']
    if not facts and not goals:raise ValueError('No complete definitions or objectives found. Upload a text-based lesson PDF, DOCX, or notes that include actual explanations.')
    if mode=='exam':
        parts+=['## Test checklist','','- Explain each goal in your own words with a correct mechanism.','- Use experimental data and controls to justify a conclusion.','- Check objectives that need additional teacher notes or textbook information.','']
    parts+=['---','','For more detailed explanations, upload explanatory lesson notes or connect the optional AI tutor.']
    return title,'\n'.join(parts)
