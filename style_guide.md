Style Guide
===========
**Borrowed from PEP8:**
> This style guide evolves over time as additional conventions are identified and past conventions are rendered obsolete by changes in the language itself.
> 
> Many projects have their own coding style guidelines. In the event of any conflicts, such project-specific guides take precedence for that project.
> One of Guido's key insights is that code is read much more often than it is written. The guidelines provided here are intended to improve the readability of code and make it consistent across the wide spectrum of [Ansible] code. As PEP 20 says, "Readability counts".
> A style guide is about consistency. Consistency with this style guide is important. Consistency within a project is more important. Consistency within one module or function is most important.
> 
> But most importantly: know when to be inconsistent -- sometimes the style guide just doesn't apply. When in doubt, use your best judgment. Look at other examples and decide what looks best. And don't hesitate to ask!
> 
> In particular: do not break backwards compatibility just to comply with this style guide!
> 
> Some other good reasons to ignore a particular guideline:
> 
> * When applying the guideline would make the code less readable, even for someone who is used to reading code that follows this guide. 
> * To be consistent with surrounding code that also breaks it (maybe for historic reasons) -- although this is also an opportunity to clean up someone else's mess (in true XP style).
> * Because the code in question predates the introduction of the guideline and there is no other reason to be modifying that code.


### [Conventions](#conventions)

#### [Line Breaks](#line_breaks)
1. One line break between tasks, blocks, and roles
1. Two line breaks between plays

#### [Play Directives](#play_params)
1. Every play should be named. No exceptions.
1. Play directives should be used in the following order
  2. name
  2. hosts
  2. connection
  2. port
  2. accelerate
  2. accelerate_port
  2. accelerate_ipv6
  2. gather_facts/gather_subset
  2. remote_user
  2. become
  2. become_user
  2. become_method
  2. max_fail_percentage
  2. ignore_errors
  2. strategy
  2. serial
  2. vars
  2. vars_files
  2. vars_prompt
  2. environment
  2. run_once
  2. pre_tasks
  2. tasks/roles (note: using tasks & roles simultaneously is discouraged)
  2. post_tasks
  3. handlers
  2. tags

#### [Task Directives](#params)
1. Every task should be named
  2. Exceptions are 
    a. include tasks where the name of the file being included is verbose enough to describe what is being included
    b. role invocation (as it doesnt work)
    c. blocks (as it doesnt work)
1. Task directives should follow this order (* denotes required)
  2. name*
  2. delegate_to
  2. delegate_facts
  2. connection
  2. no_log
  2. always_run
  2. run_once
  2. async
  2. poll
  2. become 
  2. remote_user
  2. become/become_user/become_method
  2. vars
  2. module/action + module arguments*
  2. args
  2. environment
  2. loops & loop_args
  2. retries
  2. delay
  2. when
  2. register
  2. ignore_errors/any_errors_fatal
  2. changed_when/failed_when
  2. notify
  2. tags
1. Tasks should be written out in strict YAML
```yaml
# Good
- name: Create user
  sudo: yes
  user: 
    name: linus
    state: present

# Bad
- name: Create user
  sudo: yes
  user: name=linus state=present
```

#### [Role Creation](#role_creation)

Use a tool, such as `ansible-galaxy init rolename` to create a consistent scaffold of newly created roles.

#### [Common Actions](#role_creation)

Identify a set of common actions that need to occur across of your servers:

* disabling services
* removing files
* installing packages
* configuring services

And make a "common role" that gets applied to all of your servers.


### [Anti-Patterns](#antipatterns)

#### What **NOT** to do

Do not:

* Explictly define vars that would be gathered by fact collection
* Use the shell|command|raw module when a first class module already exists
* Create a role that solely uses tasks
* Comment out parts of playbook then commit/push the change
* Don't do `when: false` to skip a task and commit/push the change
* Use lineinfile if template can be used
* Use command|shell|raw to create/change something without leveraging `creates`, `removes` or a conditional
* do not template a YAML file with Jinja2 render it, and then later import it as a variable, and try to push it to get on the following task!
* do not have entire roles, task files, or many tasks in succession that are set_facts.  If you need facts, write a facts module to collect them.  If you need to set vars for the play, in most cases you can do that by registering the output of a task, or defining the var in rolename/vars/main.yml, or in vars at the play level.
* self reference variables
```yml
appname: "{{ appname }}"
department: "{{ department }}"
```
* format an INI file as though it is yaml
* re-engineer a workaround/architecutre/etc as a result of a buggy module. Worst case, a module's source should be downloaded, placed into `library/`, patched, and used. (contributing back when/where possible is cool).
* define the exact same static variable data structure in multiple vars files.
* create a data structure soley for the purpose of aliasing module arguments and or pseudo-documentation
```yml
# BAD
# Vars File
HTTP:
 action: "ACCEPT"
 port_from: 80
 port_to: 80
 proto: "tcp"
 cidr_egress: "0.0.0.0/0"

#GOOD (this is not a full Security group, just an example)
#Task
- name: Splunk search head node security group
  local_action:
    module: ec2_group
    name: Splunk Search Head
    description: Splunk search head servers in splunk vpc belong in this group
    vpc_id: '{{ vpc.id }}'
    rules_egress:
      - proto: tcp
        port_from: 80
        port_to: 80
        proto: "tcp"
        cidr_ip: "0.0.0.0/0"

```


