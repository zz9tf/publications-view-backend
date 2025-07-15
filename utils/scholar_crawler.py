from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
import time
import re
from datetime import datetime
import logging
import threading
import concurrent.futures
import asyncio
from typing import List, Dict, Any, Optional
from schemas import WS_EVENTS, URLItem, PaperBase, URLItemStatus
from utils.socket_manager import socket_manager

logger = logging.getLogger(__name__)

class GoogleScholarSearchTask:
    """
    📋 单个Google Scholar搜索任务
    每个任务拥有独立的浏览器实例，支持并发执行
    """
    
    def __init__(self, google_scholar_url: str, client_id: str, search_id: str, headless: bool = False):
        """
        初始化搜索任务
        
        Args:
            google_scholar_url (str): Google Scholar作者页面URL
            client_id (str): 客户端ID
            search_id (str): 搜索ID
            headless (bool): 是否使用无头浏览器模式
        """
        self.google_scholar_url = google_scholar_url
        self.client_id = client_id
        self.search_id = search_id
        self.headless = headless
        
        # 🏗️ 浏览器配置
        self.options = Options()
        if headless:
            self.options.add_argument("--headless")
        self.options.add_argument("--disable-gpu")
        self.options.add_argument("--window-size=1200,800")
        self.options.add_argument("--no-sandbox")
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--disable-blink-features=AutomationControlled")
        self.options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = None
        self.wait = None
        
        # 📊 搜索状态
        self.search_data = {
            "client_id": client_id,
            "search_id": search_id,
            "url": google_scholar_url,
            "author_name": "",
            "status": URLItemStatus.PENDING,
            "progress": 0,
            "fetched_paper_count": None,
            "total_paper_count": None,
            "papers_urls": [],
            "papers": [],
            "error_message": "",
            "start_time": datetime.now().isoformat(),
            "thread_id": threading.current_thread().ident
        }
        
        self.search_data = URLItem(**self.search_data)
    
    def _initialize_driver(self):
        """🚀 初始化独立的WebDriver实例"""
        try:
            self.driver = webdriver.Chrome(options=self.options)
            self.wait = WebDriverWait(self.driver, 10)
            logger.info(f"🚀 线程 {threading.current_thread().ident} WebDriver已初始化")
            return True
        except Exception as e:
            logger.error(f"❌ 线程 {threading.current_thread().ident} WebDriver初始化失败: {str(e)}")
            self.search_data.status = URLItemStatus.ERROR
            self.search_data.error_message = f"WebDriver初始化失败: {str(e)}"
            return False
    
    async def run(self) -> Dict[str, Any]:
        """
        🎯 执行完整的搜索任务
        
        Returns:
            Dict[str, Any]: 搜索结果
        """
        try:
            logger.info(f"🎯 线程 {threading.current_thread().ident} 开始执行搜索任务: {self.search_id}")
            
            # 🚀 初始化浏览器
            if not self._initialize_driver():
                await socket_manager.send(WS_EVENTS["FAILED_FETCH_A_GOOGLE_SCHOLAR_URL"], self._serialize_search_data(), self.client_id)
                return self.search_data
            
            # 📋 收集Scholar信息
            if await self._collect_scholar_info():
                await socket_manager.send(WS_EVENTS["UPDATE_FETCH_A_GOOGLE_SCHOLAR_URL_PROCESS"], self._serialize_search_data(), self.client_id)
                # 📚 搜索论文详细信息
                await self._search_papers_details()
                await socket_manager.send(WS_EVENTS["FETCHED_COMPLETED_WITH_PAPERS_INFO"], self._serialize_search_data(), self.client_id)
            else:
                await socket_manager.send(WS_EVENTS["FAILED_FETCH_A_GOOGLE_SCHOLAR_URL"], self._serialize_search_data(), self.client_id)
            
            logger.info(f"✅ 线程 {threading.current_thread().ident} 搜索任务完成: {self.search_id}")
            
        except Exception as e:
            logger.error(f"❌ 线程 {threading.current_thread().ident} 搜索任务失败: {str(e)}")
            self.search_data.status = URLItemStatus.ERROR
            self.search_data.error_message = str(e)
        
        finally:
            # 🔒 清理资源
            self._cleanup()
        
        return self.search_data
    
    def run_sync(self) -> Dict[str, Any]:
        """
        🔄 同步包装器，用于在ThreadPoolExecutor中运行async方法
        
        Returns:
            Dict[str, Any]: 搜索结果
        """
        try:
            # 🔄 在新的事件循环中运行async方法
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.run())
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"❌ 线程 {threading.current_thread().ident} 同步包装器执行失败: {str(e)}")
            self.search_data.status = URLItemStatus.ERROR
            self.search_data.error_message = str(e)
            return self.search_data
    
    async def _collect_scholar_info(self) -> bool:
        """
        📋 收集Google Scholar作者信息和论文列表
        
        Returns:
            bool: 是否成功
        """
        try:
            self.search_data.status = URLItemStatus.COLLECTING_INFO
            logger.info(f"📋 线程 {threading.current_thread().ident} 开始收集Scholar信息...")
            
            # 🌐 访问URL
            logger.info(f"🌐 正在访问: {self.google_scholar_url}")
            self.driver.get(self.google_scholar_url)
            time.sleep(3)  # 等待页面加载
            
            # 👤 获取作者信息
            if not await self._extract_author_info():
                return False
            
            # 📅 按年份排序论文
            self._sort_papers_by_year()
            
            # 📜 加载所有论文
            self._load_all_papers()
            
            # 📊 收集论文URLs
            if not self._collect_paper_urls():
                return False
            
            self.search_data.fetched_paper_count = 0
            self.search_data.status = URLItemStatus.COLLECTED_INFO
            self.search_data.progress = 25
            logger.info(f"✅ 线程 {threading.current_thread().ident} Scholar信息收集完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 线程 {threading.current_thread().ident} 收集Scholar信息失败: {str(e)}")
            self.search_data.status = URLItemStatus.ERROR
            self.search_data.error_message = f"收集Scholar信息失败: {str(e)}"
            return False
    
    async def _extract_author_info(self) -> bool:
        """👤 提取作者信息"""
        try:
            author_selectors = [
                "#gsc_prf_in",
                ".gsc_prf_in", 
                "h1",
                ".gs_ai_name"
            ]
            
            author_name = ""
            for selector in author_selectors:
                try:
                    author_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    author_name = author_element.text.strip()
                    if author_name:
                        logger.info(f"✅ 信息区域: {selector}")
                        break
                except NoSuchElementException:
                    continue
            
            if not author_name:
                page_title = self.driver.title
                if " - " in page_title:
                    logger.info(f"✅ 页面标题: {page_title} 分割后: {page_title.split(' - ')[0].strip()}")
                    author_name = page_title.split(" - ")[0].strip()
            
            if author_name:
                self.search_data.author_name = author_name
                logger.info(f"✅ 作者信息: {author_name}")
                await socket_manager.send(WS_EVENTS["UPDATE_FETCH_A_GOOGLE_SCHOLAR_URL_PROCESS"], self._serialize_search_data(), self.client_id)
                return True
            else:
                logger.error("❌ 无法获取作者信息")
                return False
                
        except Exception as e:
            logger.error(f"❌ 提取作者信息失败: {str(e)}")
            return False
    
    def _sort_papers_by_year(self):
        """📅 按年份排序论文"""
        try:
            logger.info("📅 正在按年份排序论文...")
            
            sort_selectors = [
                "#gsc_a_ha",
                "button[aria-label*='Sort']",
                ".gsc_a_ha"
            ]
            
            sort_button = None
            for selector in sort_selectors:
                try:
                    sort_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if sort_button and sort_button.is_displayed():
                        logger.info(f"✅ 排序按钮: {selector}")
                        break
                except NoSuchElementException:
                    continue
            
            if sort_button:
                self.driver.execute_script("arguments[0].click();", sort_button)
                time.sleep(1)
                
                year_sort_options = [
                    "//button[contains(text(), 'Year')]",
                    "//a[contains(text(), 'Year')]",
                    "//option[contains(text(), 'Year')]"
                ]
                
                for xpath in year_sort_options:
                    try:
                        year_option = self.driver.find_element(By.XPATH, xpath)
                        logger.info(f"✅ 年份排序选项: {xpath}")
                        self.driver.execute_script("arguments[0].click();", year_option)
                        time.sleep(1)
                        break
                    except NoSuchElementException:
                        continue
            
            logger.info("✅ 论文已按年份排序")
            
        except Exception as e:
            logger.warning(f"⚠️ 按年份排序失败，将使用默认排序: {str(e)}")
    
    def _load_all_papers(self):
        """📜 加载所有论文（点击Show more）"""
        try:
            logger.info("📜 正在加载所有论文...")
            show_more_attempts = 0
            max_attempts = 1000
            
            initial_papers = self.driver.find_elements(By.CSS_SELECTOR, ".gsc_a_tr")
            logger.info(f"📋 初始论文数量: {len(initial_papers)}")
            
            while show_more_attempts < max_attempts:
                try:
                    show_more_selectors = [
                        "#gsc_bpf_more",
                        "button[onclick*='more']",
                        ".gsc_bpf_more",
                        "//button[contains(text(), 'Show more')]",
                        "//button[contains(text(), 'SHOW MORE')]",
                        "//a[contains(text(), 'Show more')]"
                    ]
                    
                    show_more_button = None
                    for selector in show_more_selectors:
                        try:
                            if selector.startswith("//"):
                                show_more_button = self.driver.find_element(By.XPATH, selector)
                            else:
                                show_more_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                            
                            if show_more_button and show_more_button.is_displayed() and show_more_button.is_enabled():
                                break
                        except NoSuchElementException:
                            continue
                    
                    if show_more_button and show_more_button.is_displayed() and show_more_button.is_enabled():
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", show_more_button)
                        time.sleep(1)
                        self.driver.execute_script("arguments[0].click();", show_more_button)
                        logger.info(f"🔄 点击Show more按钮 (第{show_more_attempts + 1}次)")
                        time.sleep(2)
                        show_more_attempts += 1
                    else:
                        logger.info("✅ 没有更多论文可加载")
                        break
                        
                except Exception as e:
                    logger.warning(f"⚠️ 点击Show more按钮失败: {str(e)}")
                    break
            
        except Exception as e:
            logger.warning(f"⚠️ 加载论文失败: {str(e)}")
    
    def _collect_paper_urls(self) -> bool:
        """📊 收集所有论文URL"""
        try:
            logger.info("📊 正在收集论文信息...")
            
            paper_selectors = [
                ".gsc_a_tr",
                "tr.gsc_a_tr",
                ".gs_r.gs_or.gs_scl",
                ".gsc_a_t"
            ]
            
            papers_urls = []
            paper_elements = []
            
            for selector in paper_selectors:
                try:
                    paper_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if paper_elements:
                        break
                except NoSuchElementException:
                    continue
            
            if paper_elements:
                for paper_element in paper_elements:
                    try:
                        link_selectors = [
                            "a.gsc_a_at",
                            "a",
                            ".gsc_a_at"
                        ]
                        
                        paper_url = None
                        for link_selector in link_selectors:
                            try:
                                link_element = paper_element.find_element(By.CSS_SELECTOR, link_selector)
                                paper_url = link_element.get_attribute("href")
                                if paper_url and paper_url.startswith("http"):
                                    break
                            except NoSuchElementException:
                                continue
                        
                        if paper_url and paper_url not in papers_urls:
                            papers_urls.append(paper_url)
                            
                    except Exception as e:
                        logger.warning(f"⚠️ 提取论文URL失败: {str(e)}")
                        continue
            
            total_paper_count = len(papers_urls)
            self.search_data.total_paper_count = total_paper_count
            self.search_data.papers_urls = papers_urls
            
            logger.info(f"✅ 成功收集到 {total_paper_count} 篇论文")
            logger.info(f"📋 论文URL样例: {papers_urls[:3] if papers_urls else '无'}")
            
            return total_paper_count > 0
            
        except Exception as e:
            logger.error(f"❌ 收集论文信息失败: {str(e)}")
            return False
    
    async def _search_papers_details(self):
        """📚 搜索论文详细信息"""
        try:
            papers_urls = self.search_data.papers_urls
            if not papers_urls:
                logger.warning("⚠️ 没有找到论文URL")
                return
            
            logger.info(f"📚 开始获取 {len(papers_urls)} 篇论文的详细信息...")
            self.search_data.status = URLItemStatus.SEARCHING_PAPERS
            
            papers = []
            
            for index, paper_url in enumerate(papers_urls):
                self.search_data.fetched_paper_count = index + 1
                self.search_data.progress = 25 + round((index + 1)*1.0 / len(papers_urls) * 70, 2)
                try:
                    logger.info(f"📄 正在处理第 {index + 1}/{len(papers_urls)} 篇论文...")
                    
                    # 🌐 访问论文页面
                    self.driver.get(paper_url)
                    time.sleep(2)
                    
                    # 📋 提取论文信息
                    paper_info = self._extract_paper_details(paper_url)
                    
                    if paper_info:
                        papers.append(paper_info)
                        logger.info(f"✅ 成功提取论文: {paper_info.title[:50]}...")
                    else:
                        logger.warning(f"⚠️ 无法提取论文信息: {paper_url}")
                    
                except Exception as e:
                    logger.error(f"❌ 处理论文失败 {paper_url}: {str(e)}")
                    continue
                await socket_manager.send(WS_EVENTS["UPDATE_FETCH_A_GOOGLE_SCHOLAR_URL_PROCESS"], self._serialize_search_data(), self.client_id)
            
            # 📊 更新最终结果
            self.search_data.papers = papers
            self.search_data.status = URLItemStatus.COMPLETED
            self.search_data.progress = 100
            
            logger.info(f"✅ 论文详细信息搜索完成，成功获取 {len(papers)} 篇论文")
            
        except Exception as e:
            logger.error(f"❌ 搜索论文详细信息失败: {str(e)}")
            self.search_data.status = URLItemStatus.ERROR
            self.search_data.error_message = f"搜索论文详细信息失败: {str(e)}"
    
    def _serialize_search_data(self) -> dict:
        """
        🔄 序列化搜索数据，处理datetime等不可JSON序列化的对象
        
        Returns:
            dict: 可JSON序列化的搜索数据
        """
        try:
            # 使用model_dump并指定序列化模式
            return self.search_data.model_dump(mode='json')
        except Exception as e:
            logger.warning(f"⚠️ 序列化搜索数据失败: {str(e)}")
            # 备用方案：手动处理
            data = self.search_data.model_dump()
            
            # 处理datetime字段
            if 'start_time' in data and data['start_time']:
                if isinstance(data['start_time'], str):
                    pass  # 已经是字符串
                else:
                    data['start_time'] = data['start_time'].isoformat() if data['start_time'] else None
            
            # 处理papers中的datetime字段
            if 'papers' in data and data['papers']:
                for paper in data['papers']:
                    if 'date' in paper and paper['date']:
                        if not isinstance(paper['date'], str):
                            paper['date'] = paper['date'].isoformat() if paper['date'] else ""
            
            return data
    
    def _extract_paper_details(self, paper_url: str) -> Optional[PaperBase]:
        """📄 提取单篇论文的详细信息"""
        try:
            paper_info = {
                "title": "",
                "authors": [],
                "year": 0,  # 默认值为0，稍后会更新
                "date": "",
                "url": paper_url,
                "pdf_url": None,
                "citations": 0,  # 默认值为0，稍后会更新
                "publisher": None,
                "paper_type": None,
                "description": None
            }
            
            # 📑 提取标题
            title_selectors = [
                ".gs_rt h3 a",
                ".gs_rt a",
                "h1",
                ".citation_title",
                "title"
            ]
            
            for selector in title_selectors:
                try:
                    title_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    title = title_element.text.strip()
                    if title and len(title) > 5:
                        paper_info["title"] = title
                        break
                except NoSuchElementException:
                    continue
            
            # 👥 提取作者信息
            authors_selectors = [
                ".gs_a",
                ".citation_author",
                ".authors",
                ".author"
            ]
            
            for selector in authors_selectors:
                try:
                    authors_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    authors_text = authors_element.text.strip()
                    if authors_text:
                        authors = self._parse_authors(authors_text)
                        if authors:
                            paper_info["authors"] = authors
                            break
                except NoSuchElementException:
                    continue
            
            # 📅 提取年份和日期
            year_selectors = [
                ".gs_a",
                ".citation_date",
                ".year",
                ".date"
            ]
            
            for selector in year_selectors:
                try:
                    date_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    date_text = date_element.text.strip()
                    year, date = self._parse_date_info(date_text)
                    if year:
                        paper_info["year"] = year
                        paper_info["date"] = date
                        break
                except NoSuchElementException:
                    continue
            
            # 🔗 提取PDF或论文库URL
            pdf_selectors = [
                "a[href*='.pdf']",
                ".gs_or_ggsm a",
                ".citation_pdf_url",
                "a[href*='doi.org']",
                "a[href*='arxiv.org']"
            ]
            
            for selector in pdf_selectors:
                try:
                    pdf_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for pdf_element in pdf_elements:
                        href = pdf_element.get_attribute("href")
                        if href and (href.endswith('.pdf') or 'doi.org' in href or 'arxiv.org' in href):
                            paper_info["pdf_url"] = href
                            break
                    if paper_info["pdf_url"]:
                        break
                except NoSuchElementException:
                    continue
            
            # 📊 提取引用次数
            citation_selectors = [
                ".gs_fl a[href*='cites']",
                ".citation_count",
                "a[href*='cited']"
            ]
            
            for selector in citation_selectors:
                try:
                    citation_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    citation_text = citation_element.text.strip()
                    citations = self._parse_citations(citation_text)
                    if citations is not None:
                        paper_info["citations"] = citations
                        break
                except NoSuchElementException:
                    continue
            
            # 📰 提取发表信息和类型
            publisher_selectors = [
                ".gs_a",
                ".citation_venue",
                ".journal",
                ".conference"
            ]
            
            for selector in publisher_selectors:
                try:
                    publisher_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    publisher_text = publisher_element.text.strip()
                    publisher, paper_type = self._parse_publisher_info(publisher_text)
                    if publisher:
                        paper_info["publisher"] = publisher
                        paper_info["paper_type"] = paper_type
                        break
                except NoSuchElementException:
                    continue
            
            # 📝 提取描述信息
            description_selectors = [
                ".gs_rs",
                ".citation_abstract",
                ".abstract",
                ".description"
            ]
            
            for selector in description_selectors:
                try:
                    desc_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    description = desc_element.text.strip()
                    if description and len(description) > 20:
                        paper_info["description"] = description[:500]
                        break
                except NoSuchElementException:
                    continue
            
            if not paper_info["title"]:
                return None
            
            # 🔧 创建PaperBase对象
            try:
                # 确保必需字段有有效值
                if not paper_info["date"]:
                    paper_info["date"] = f"{paper_info['year']}-01-01" if paper_info["year"] > 0 else "1900-01-01"
                
                paper_base = PaperBase(**paper_info)
                return paper_base
            except Exception as e:
                logger.error(f"❌ 创建PaperBase对象失败: {str(e)}")
                return None
            
        except Exception as e:
            logger.error(f"❌ 提取论文详细信息失败: {str(e)}")
            return None
    
    def _parse_authors(self, authors_text: str) -> List[str]:
        """👥 解析作者信息"""
        try:
            if " - " in authors_text:
                authors_text = authors_text.split(" - ")[0]
            
            authors = [author.strip() for author in authors_text.split(",")]
            
            cleaned_authors = []
            for author in authors:
                author = re.sub(r'\d{4}', '', author).strip()
                author = re.sub(r'[^\w\s\-\.]', '', author).strip()
                if author and len(author) > 1:
                    cleaned_authors.append(author)
            
            return cleaned_authors
            
        except Exception as e:
            logger.warning(f"⚠️ 解析作者信息失败: {str(e)}")
            return []
    
    def _parse_date_info(self, date_text: str) -> tuple:
        """📅 解析日期信息"""
        try:
            year_match = re.search(r'\b(19|20)\d{2}\b', date_text)
            year = int(year_match.group()) if year_match else None
            
            date_patterns = [
                r'\b\d{4}-\d{2}-\d{2}\b',
                r'\b\d{1,2}/\d{1,2}/\d{4}\b',
                r'\b\d{1,2}-\d{1,2}-\d{4}\b'
            ]
            
            date_str = ""
            for pattern in date_patterns:
                date_match = re.search(pattern, date_text)
                if date_match:
                    date_str = date_match.group()
                    break
            
            if not date_str and year:
                logger.warning(f"⚠️ 解析日期信息失败: {date_text}")
                date_str = f"{year}-01-01"
            
            return year, date_str
            
        except Exception as e:
            logger.warning(f"⚠️ 解析日期信息失败: {str(e)}")
            return -1, ""
    
    def _parse_citations(self, citation_text: str) -> int:
        """📊 解析引用次数"""
        try:
            patterns = [
                r'Cited by (\d+)',
                r'引用 (\d+)',
                r'(\d+) citations',
                r'(\d+)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, citation_text, re.IGNORECASE)
                if match:
                    return int(match.group(1))
            
            return 0
            
        except Exception as e:
            logger.warning(f"⚠️ 解析引用次数失败: {str(e)}")
            return 0
    
    def _parse_publisher_info(self, publisher_text: str) -> tuple:
        """📰 解析发表商和论文类型信息"""
        try:
            publisher = publisher_text
            paper_type = ""
            
            bracket_pattern = r'\([^)]*\)'
            publisher_clean = re.sub(bracket_pattern, '', publisher_text).strip()
            
            if publisher_clean:
                publisher = publisher_clean
            
            text_lower = publisher_text.lower()
            
            if any(keyword in text_lower for keyword in ['journal', 'nature', 'science', 'ieee', 'acm']):
                paper_type = "Journal"
            elif any(keyword in text_lower for keyword in ['conference', 'proceedings', 'workshop', 'symposium']):
                paper_type = "Conference"
            elif any(keyword in text_lower for keyword in ['arxiv', 'preprint', 'biorxiv']):
                paper_type = "Preprint"
            else:
                paper_type = "Unknown"
            
            return publisher, paper_type
            
        except Exception as e:
            logger.warning(f"⚠️ 解析发表商信息失败: {str(e)}")
            return "", ""
    
    def _cleanup(self):
        """🔒 清理资源"""
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
                self.wait = None
                logger.info(f"🔒 线程 {threading.current_thread().ident} 浏览器已关闭")
        except Exception as e:
            logger.warning(f"⚠️ 线程 {threading.current_thread().ident} 关闭浏览器失败: {str(e)}")


class GoogleScholarCrawler:
    """
    🔍 Google Scholar 论文爬虫管理器
    支持多线程并发搜索，每个任务使用独立的浏览器实例
    """
    
    def __init__(self, max_workers: int = 3, headless: bool = False):
        """
        初始化爬虫管理器
        
        Args:
            max_workers (int): 最大并发线程数
            headless (bool): 是否使用无头浏览器模式
        """
        self.max_workers = max_workers
        self.headless = headless
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.running_tasks = {}  # 存储正在运行的任务
        self.completed_tasks = {}  # 存储已完成的任务
        self.completed_tasks_order = []  # 📋 记录完成任务的顺序
        self.max_completed_tasks = 20  # 🔢 最大保存的完成任务数量
        self._task_lock = threading.Lock()
        
        logger.info(f"🚀 Google Scholar 爬虫管理器已初始化，最大并发数: {max_workers}")
    
    def scholar_info(self, google_scholar_url: str, client_id: str, search_id: str) -> str:
        """
        🎯 提交搜索任务（异步执行）
        
        Args:
            google_scholar_url (str): Google Scholar作者页面URL
            client_id (str): 客户端ID
            search_id (str): 搜索ID
        Returns:
            str: 任务ID
        """
        task_id = f"{client_id}_{search_id}"
        
        with self._task_lock:
            # 检查是否已有相同任务在运行
            if task_id in self.running_tasks:
                logger.warning(f"⚠️ 任务 {task_id} 已在运行中")
                return task_id
            
            # 创建搜索任务
            search_task = GoogleScholarSearchTask(
                google_scholar_url=google_scholar_url,
                client_id=client_id,
                search_id=search_id,
                headless=self.headless
            )
            
            # 提交到线程池（使用同步包装器）
            future = self.executor.submit(search_task.run_sync)
            
            # 添加回调函数处理完成的任务
            future.add_done_callback(lambda f: self._on_task_complete(task_id, f))
            
            self.running_tasks[task_id] = {
                "future": future,
                "task": search_task,
                "start_time": datetime.now()
            }
            
            logger.info(f"🎯 任务 {task_id} 已提交到线程池")
            return task_id
    
    def _on_task_complete(self, task_id: str, future: concurrent.futures.Future):
        """📊 任务完成回调"""
        with self._task_lock:
            if task_id in self.running_tasks:
                task_info = self.running_tasks.pop(task_id)
                
                try:
                    result = future.result()
                    self.completed_tasks[task_id] = {
                        "result": result,
                        "completed_time": datetime.now(),
                        "start_time": task_info["start_time"]
                    }
                    logger.info(f"✅ 任务 {task_id} 已完成")
                except Exception as e:
                    logger.error(f"❌ 任务 {task_id} 执行失败: {str(e)}")
                    self.completed_tasks[task_id] = {
                        "result": {"status": "error", "error_message": str(e)},
                        "completed_time": datetime.now(),
                        "start_time": task_info["start_time"]
                    }
                
                # 📋 管理完成任务列表，保持最多20个记录
                self._manage_completed_tasks(task_id)
    
    def _manage_completed_tasks(self, new_task_id: str):
        """
        📋 管理完成任务列表，保持最多20个记录（按时间顺序）
        
        Args:
            new_task_id (str): 新完成的任务ID
        """
        # 添加新任务到顺序列表
        if new_task_id not in self.completed_tasks_order:
            self.completed_tasks_order.append(new_task_id)
        
        # 🔢 如果超过最大数量，删除最早的任务
        while len(self.completed_tasks_order) > self.max_completed_tasks:
            oldest_task_id = self.completed_tasks_order.pop(0)  # 移除最早的任务ID
            
            if oldest_task_id in self.completed_tasks:
                del self.completed_tasks[oldest_task_id]  # 删除对应的任务数据
                logger.info(f"🗑️ 删除最早的完成任务记录: {oldest_task_id}")
        
        logger.info(f"📊 当前保存 {len(self.completed_tasks_order)} 个完成任务记录")
    
    def get_search_status(self, client_id: str, search_id: str) -> Dict[str, Any]:
        """
        📊 获取搜索状态信息
        
        Args:
            client_id (str): 客户端ID
            search_id (str): 搜索ID
        Returns:
            Dict[str, Any]: 搜索状态信息
        """
        task_id = f"{client_id}_{search_id}"
        
        with self._task_lock:
            # 检查运行中的任务
            if task_id in self.running_tasks:
                task_info = self.running_tasks[task_id]
                search_task = task_info["task"]
                return {
                    **search_task.search_data,
                    "task_status": "running",
                    "start_time": task_info["start_time"].isoformat()
                }
            
            # 检查已完成的任务
            if task_id in self.completed_tasks:
                task_info = self.completed_tasks[task_id]
                return {
                    **task_info["result"],
                    "task_status": "completed",
                    "start_time": task_info["start_time"].isoformat(),
                    "completed_time": task_info["completed_time"].isoformat()
                }
        
        return {
            "status": "not_found", 
            "error": "搜索记录不存在",
            "task_status": "not_found"
        }
    
    def get_all_tasks_status(self) -> Dict[str, Any]:
        """
        📋 获取所有任务状态
        
        Returns:
            Dict[str, Any]: 所有任务状态
        """
        with self._task_lock:
            return {
                "running_tasks": len(self.running_tasks),
                "completed_tasks": len(self.completed_tasks),
                "max_workers": self.max_workers,
                "max_completed_tasks": self.max_completed_tasks,
                "running_task_ids": list(self.running_tasks.keys()),
                "completed_task_ids": self.completed_tasks_order.copy(),  # 📋 按时间顺序返回
                "completed_task_ids_count": len(self.completed_tasks_order)
            }
    
    def cancel_task(self, client_id: str, search_id: str) -> bool:
        """
        🛑 取消搜索任务
        
        Args:
            client_id (str): 客户端ID
            search_id (str): 搜索ID
        Returns:
            bool: 是否成功取消
        """
        task_id = f"{client_id}_{search_id}"
        
        with self._task_lock:
            if task_id in self.running_tasks:
                task_info = self.running_tasks[task_id]
                future = task_info["future"]
                
                # 尝试取消任务
                cancelled = future.cancel()
                
                if cancelled:
                    # 清理资源
                    search_task = task_info["task"]
                    search_task._cleanup()
                    
                    self.running_tasks.pop(task_id)
                    logger.info(f"🛑 任务 {task_id} 已取消")
                    return True
                else:
                    logger.warning(f"⚠️ 无法取消任务 {task_id}，任务可能已在执行中")
                    return False
        
        return False
    
    def get_recent_completed_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        📋 获取最近完成的任务列表
        
        Args:
            limit (int): 返回的任务数量限制
        Returns:
            List[Dict[str, Any]]: 最近完成的任务列表（按时间倒序）
        """
        with self._task_lock:
            # 获取最近的任务ID（倒序）
            recent_task_ids = self.completed_tasks_order[-limit:] if limit > 0 else self.completed_tasks_order
            recent_task_ids.reverse()  # 最新的在前面
            
            recent_tasks = []
            for task_id in recent_task_ids:
                if task_id in self.completed_tasks:
                    task_data = self.completed_tasks[task_id].copy()
                    task_data["task_id"] = task_id
                    recent_tasks.append(task_data)
            
            return recent_tasks
    
    def shutdown(self, wait: bool = True):
        """
        🔒 关闭爬虫管理器
        
        Args:
            wait (bool): 是否等待所有任务完成
        """
        logger.info("🔒 正在关闭Google Scholar爬虫管理器...")
        
        with self._task_lock:
            # 清理所有运行中任务的资源
            for task_id, task_info in self.running_tasks.items():
                try:
                    search_task = task_info["task"]
                    search_task._cleanup()
                except Exception as e:
                    logger.warning(f"⚠️ 清理任务 {task_id} 资源失败: {str(e)}")
        
        # 关闭线程池
        self.executor.shutdown(wait=wait)
        logger.info("🔒 Google Scholar爬虫管理器已关闭")


# 创建全局实例
scholar_crawler = GoogleScholarCrawler(max_workers=5, headless=False) 