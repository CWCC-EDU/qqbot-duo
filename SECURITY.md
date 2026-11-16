# 敏感信息与问题反馈

不要在Issue或提交中附上真实.env、API密钥、QQ登录信息、完整数据库或聊天记录。

提交问题时只提供去除账号和密钥后的错误堆栈、插件名称和复现步骤。私密数据请先在本机检查和删去。

如果意外提交有效密钥，应先撤销或轮换，再处理仓库历史；仅在最新版本删掉文件不能撤销已泄露的密钥。参考 [GitHub敏感信息处理文档](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)。

本项目是两套历史插件的整合，并非经过完整安全审计的框架。部署时请保持管理端口仅本机可访问，按需启用插件和后台，不将运行目录直接提交。
